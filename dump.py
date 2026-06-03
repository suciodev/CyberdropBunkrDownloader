import requests
import json
import argparse
import sys
import os
import re
import time
from tenacity import retry, wait_fixed, retry_if_exception_type, stop_after_attempt
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from tqdm import tqdm
from base64 import b64decode
from math import floor
from urllib.parse import unquote
from datetime import datetime

BUNKR_VS_API_URL_FOR_SLUG = "https://bunkr.cr/api/vs"
BUNKR_SIGN_API_URL = "https://glb-apisign.cdn.cr/sign"
SECRET_KEY_BASE = "SECRET_KEY_"

MAX_RETRIES=10

def get_items_list(session, url, extensions, only_export, custom_path=None, is_last_page=True, date_before=None, date_after=None):
    extensions_list = extensions.split(',') if extensions is not None else []
       
    r = session.get(url)
    if r.status_code != 200:
        raise Exception(f"[-] HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, 'html.parser')
    is_bunkr = "| Bunkr" in soup.find('title').text

    direct_link = False
    
    if is_bunkr:
        items = []
        soup = BeautifulSoup(r.content, 'html.parser')

        direct_link = soup.find('span', {'class': 'ic-videos'}) is not None or soup.find('div', {'class': 'lightgallery'}) is not None
        if direct_link:
            album_name = soup.find('h1', {'class': 'text-[20px]'})
            if album_name is None:
                album_name = soup.find('h1', {'class': 'truncate'})

            album_name = remove_illegal_chars(album_name.text)
            # collect individual file links on album page instead of treating album as a single file
            file_links = soup.find_all('a', href=re.compile(r'/f/'))
            if file_links:
                for a in file_links:
                    href = a.get('href')
                    full_url = urljoin(url, href)
                    title = a.get('title') or (a.text.strip() if a.text else None)
                    items.append({'url': full_url, 'size': -1, 'name': remove_illegal_chars(title) if title else None})
            else:
                # fallback: try resolving the album page as a single file
                items.append(get_real_download_url(session, url, True))
        else:
            theItems = soup.find_all('div', {'class': 'theItem'})
            for theItem in theItems:
                if date_before is not None or date_after is not None:
                    date_span = theItem.find('span', {'class': 'ic-clock'})
                    if not is_date_in_range(date_span.text, date_before, date_after):
                        continue
                box = theItem.find('a', {'class': 'after:absolute'})
                items.append({'url': box['href'], 'size': -1, 'name': theItem.find('p').text})
            
            album_name = soup.find('h1', {'class': 'truncate'}).text
            album_name = remove_illegal_chars(album_name)
    else:
        items = []
        items_dom = soup.find_all('a', {'class': 'image'})
        for item_dom in items_dom:
            items.append({'url': f"https://cyberdrop.me{item_dom['href']}", 'size': -1})
        album_name = remove_illegal_chars(soup.find('h1', {'id': 'title'}).text)

    download_path = get_and_prepare_download_path(custom_path, album_name)
    already_downloaded_url = get_already_downloaded_url(download_path)

    for item in items:
        if not direct_link:
            item = get_real_download_url(session, item['url'], is_bunkr, item['name'], item['url'])
            if item is None:
                print(f"\t\t[-] Unable to find a download link")
                continue

        download_tracking_value = get_download_tracking_value(item)
        extension = get_url_data(item['url'])['extension']
        if ((extension in extensions_list or len(extensions_list) == 0) and (download_tracking_value not in already_downloaded_url)):
            if only_export:
                write_url_to_list(item['url'], download_path)
            else:
                download(session, item['url'], download_path, is_bunkr, item['name'], download_tracking_value)
        
    pagination = soup.find('nav', {'class': 'pagination'})
    if pagination is not None:
        current_page = int(pagination.find('span', {'class': 'active'}).text)
        page_links = [a for a in pagination.find_all('a') if a.text.strip().isdigit()]
        last_page = int(page_links[-1].text) if page_links else current_page

        if int(current_page) < int(last_page):
            url_next_page = None
            print(f"[!] Downloading page ({int(current_page)+1}/{last_page})")
            if re.search(r'([?&])page=\d+', url):
                url_next_page = re.sub(r'([?&])page=\d+', r'\1page={}'.format(current_page+1), url)
            else:
                url_next_page = f"{url}{'&' if '?' in url else '?'}page={(current_page+1)}"
        
            get_items_list(session, url_next_page, extensions, only_export, custom_path=custom_path, is_last_page=(int(current_page) == int(last_page)), date_before=args.before, date_after=args.after)

    if is_last_page:
        print(f"\t[+] File list exported in {os.path.join(download_path, 'url_list.txt')}" if only_export else f"\t[+] Download completed")
    return
    
def get_real_download_url(session, url, is_bunkr=True, item_name=None, download_key=None):

    if is_bunkr:
        url = url if 'https' in url else f'https://bunkr.cr{url}'
    else:
        url = url.replace('/f/','/api/f/')

    r = session.get(url)
    if r.status_code != 200:
        print(f"\t[-] HTTP error {r.status_code} getting real url for {url}")
        return None
           
    if is_bunkr:
        # Extract file ID and filename from the file page
        file_path = None
        original_filename = extract_bunkr_filename(r.text)
        cdn_url = extract_bunkr_cdn_url(r.text)
        
        print(f"\t\t[DEBUG] Extracted filename: '{original_filename}'")
        print(f"\t\t[DEBUG] Extracted cdn url: '{cdn_url}'")

        if cdn_url:
            sign_url = get_signed_download_url(session, cdn_url, r.url)
            if sign_url:
                return {'url': sign_url, 'size': -1, 'name': item_name or remove_illegal_chars(original_filename or get_url_data(cdn_url)['file_name']), 'download_key': download_key or url}
        
        if original_filename:
            # Construct the file path for the sign API
            file_path = f"storage/media/{original_filename.replace(' ', '-')}"
            print(f"\t\t[DEBUG] Trying file_path: {file_path}")
            # Try with the actual filename format
            sign_url = get_signed_download_url(session, file_path, r.url)
            if sign_url:
                return {'url': sign_url, 'size': -1, 'name': item_name or remove_illegal_chars(original_filename), 'download_key': download_key or url}
            
            # If that fails, try alternate path format (with spaces)
            file_path = f"storage/media/{original_filename}"
            print(f"\t\t[DEBUG] Trying file_path (alt): {file_path}")
            sign_url = get_signed_download_url(session, file_path, r.url)
            if sign_url:
                return {'url': sign_url, 'size': -1, 'name': item_name or remove_illegal_chars(original_filename), 'download_key': download_key or url}
        
        # Fallback: try legacy encryption method
        m_id2 = re.search(r'href="/f/([A-Za-z0-9_-]+)"', r.text)
        if m_id2:
            slug = m_id2.group(1)
            encryption_data = get_encryption_data(slug)
            if encryption_data is not None:
                return {'url': decrypt_encrypted_url(encryption_data), 'size': -1, 'name': item_name}
        
        print(f"\t\t[-] Unable to extract file info from {r.url}")
        return None
    else:
        item_data = json.loads(r.content)
        return {'url': item_data['url'], 'size': -1, 'name': item_data['name'], 'download_key': download_key or url}

def extract_bunkr_filename(html):
    soup = BeautifulSoup(html, 'html.parser')

    candidates = []

    the_item = soup.find('div', class_='theItem')
    if the_item:
        candidates.append(the_item.get('title'))

        the_name = the_item.find('p', class_='theName')
        if the_name:
            candidates.append(the_name.get_text(strip=True))

        hidden_p = the_item.find('p', style=re.compile(r'display:\s*none'))
        if hidden_p:
            candidates.append(hidden_p.get_text(strip=True))

        thumb_img = the_item.find('img', class_='grid-images_box-img')
        if thumb_img and thumb_img.get('src'):
            match = re.search(r'/thumbs/([^"/]+)\.png', thumb_img['src'])
            if match:
                candidates.append(f"{match.group(1)}.mp4")

    heading = soup.find('h1')
    if heading:
        candidates.append(heading.get_text(strip=True))

    og_title = soup.find('meta', property='og:title')
    if og_title:
        candidates.append(og_title.get('content'))

    title = soup.find('title')
    if title:
        candidates.append(re.sub(r'\s*\|\s*Bunkr\s*$', '', title.get_text(strip=True)))

    for candidate in candidates:
        filename = clean_bunkr_filename(candidate)
        if filename:
            return filename

    return None

def extract_bunkr_cdn_url(html):
    match = re.search(r'var\s+jsCDN\s*=\s*"([^"]+)"', html)
    if match:
        return decode_bunkr_js_string(match.group(1))

    match = re.search(r'https://[^"\']+\.cdn\.cr/storage/media/[^"\']+', html)
    if match:
        return decode_bunkr_js_string(match.group(0))

    return None

def clean_bunkr_filename(value):
    if not value:
        return None

    filename = unquote(value).strip()
    if not filename or re.fullmatch(r'v?\d+(?:\.\d+){1,3}', filename, flags=re.IGNORECASE):
        return None

    if filename.lower() in ('bunkr', 'version'):
        return None

    if not os.path.splitext(filename)[1]:
        return None

    return filename

def decode_bunkr_js_string(value):
    return json.loads(f'"{value}"')

def get_download_tracking_value(item):
    return item.get('download_key', item['url'])
        
@retry(retry=retry_if_exception_type(requests.exceptions.ConnectionError), wait=wait_fixed(2), stop=stop_after_attempt(MAX_RETRIES))
def download(session, item_url, download_path, is_bunkr=False, file_name=None, download_key=None):

    file_name = get_url_data(item_url)['file_name'] if file_name is None else file_name
    if os.path.exists(file_name):
        file_name = f"{int(time.time())}_{file_name}"

    final_path = os.path.join(download_path, file_name)

    with session.get(item_url, stream=True, timeout=5) as r:
        print(f"\t[+] Downloading {item_url} ({file_name})")
        if r.status_code != 200:
            print(f"\t\t[-] Error downloading \"{file_name}\": {r.status_code}")
            return
        if r.url == "https://bnkr.b-cdn.net/maintenance.mp4":
            print(f"\t\t[-] Error downloading \"{file_name}\": Server is down for maintenance")
            return

        file_size = int(r.headers.get('content-length', -1))
        with open(final_path, 'wb') as f:
            with tqdm(total=file_size, unit='iB', unit_scale=True, desc=file_name, leave=False) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk is not None:
                        f.write(chunk)
                        pbar.update(len(chunk))

    if is_bunkr and file_size > -1:
        downloaded_file_size = os.stat(final_path).st_size
        if downloaded_file_size != file_size:
            print(f"\t[-] {file_name} size check failed, file could be broken\n")
            return

    mark_as_downloaded(download_key or item_url, download_path)

    return

def create_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        'Referer': 'https://bunkr.cr/',
    })
    return session

def get_url_data(url):
    parsed_url = urlparse(url)
    return {'file_name': os.path.basename(parsed_url.path), 'extension': os.path.splitext(parsed_url.path)[1], 'hostname': parsed_url.hostname}

def get_and_prepare_download_path(custom_path, album_name):

    final_path = 'downloads' if custom_path is None else custom_path
    final_path = os.path.join(final_path, album_name) if album_name is not None else 'downloads'
    final_path = final_path.replace('\n', '')

    if not os.path.isdir(final_path):
        os.makedirs(final_path)

    already_downloaded_path = os.path.join(final_path, 'already_downloaded.txt')
    if not os.path.isfile(already_downloaded_path):
        open(already_downloaded_path, 'w', encoding='utf-8').close()

    return final_path

def write_url_to_list(item_url, download_path):

    list_path = os.path.join(download_path, 'url_list.txt')

    with open(list_path, 'a', encoding='utf-8') as f:
        f.write(f"{item_url}\n")

    return

def get_already_downloaded_url(download_path):

    file_path = os.path.join(download_path, 'already_downloaded.txt')

    if not os.path.isfile(file_path):
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read().splitlines()

def mark_as_downloaded(item_url, download_path):

    file_path = os.path.join(download_path, 'already_downloaded.txt')
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"{item_url}\n")

    return

def remove_illegal_chars(string):
    return re.sub(r'[<>:"/\\|?*\']|[\0-\31]', "-", string).strip()

def get_signed_download_url(session, file_path, file_page_url):
    """
    Get a signed CDN download URL using the /sign API endpoint.
    file_path can be a full CDN URL or a path like "storage/media/filename.mp4"
    """
    try:
        if re.match(r'^https?://', file_path):
            parsed_url = urlparse(file_path)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
            signed_path = unquote(parsed_url.path)
        else:
            signed_path = f"/{file_path.lstrip('/')}"
            base_url = f"https://glb-cdn.cdn.cr{signed_path}"

        headers = {
            'Origin': 'https://bunkr.cr',
            'Referer': file_page_url
        }
        r = session.get(BUNKR_SIGN_API_URL, params={'path': signed_path}, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"\t\t[-] HTTP ERROR {r.status_code} getting signed URL")
            return None
        
        data = json.loads(r.content)
        ex = data.get('ex')
        token = data.get('token')
        
        if ex and token:
            # Construct the signed CDN URL
            signed_url = f"{base_url}?ex={ex}&token={token}"
            return signed_url
        else:
            print(f"\t\t[-] Invalid response from sign API: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"\t\t[-] Exception in get_signed_download_url: {e}")
        return None

def get_encryption_data(slug=None):

    payload = {'slug': slug}
    headers = {
        'Origin': 'https://bunkr.cr',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': session.headers.get('Referer', 'https://bunkr.cr/')
    }
    try:
        r = session.post(BUNKR_VS_API_URL_FOR_SLUG, json=payload, timeout=10, headers=headers)
    except Exception as e:
        print(f"\t\t[-] Exception posting to {BUNKR_VS_API_URL_FOR_SLUG}: {e}")
        return None

    # Diagnostic logging for debugging API 404s
    if r.status_code != 200:
        print(f"\t\t[-] HTTP ERROR {r.status_code} getting encryption data")
        try:
            req_body = r.request.body.decode('utf-8') if r.request.body else ''
        except Exception:
            req_body = str(r.request.body)
        print(f"\t\t    Request payload: {req_body}")
        print(f"\t\t    Sent headers: {headers}")
        print(f"\t\t    Response body: {r.text[:1000]}")
        return None
    
    try:
        return json.loads(r.content)
    except Exception as e:
        print(f"\t\t[-] Failed to parse encryption data JSON: {e}")
        print(f"\t\t    Response body: {r.text[:1000]}")
        return None

def decrypt_encrypted_url(encryption_data):

    secret_key = f"{SECRET_KEY_BASE}{floor(encryption_data['timestamp'] / 3600)}"
    encrypted_url_bytearray = list(b64decode(encryption_data['url']))
    secret_key_byte_array = list(secret_key.encode('utf-8'))

    decrypted_url = ""

    for i in range(len(encrypted_url_bytearray)):
        decrypted_url += chr(encrypted_url_bytearray[i] ^ secret_key_byte_array[i % len(secret_key_byte_array)])

    return decrypted_url

def date_argument(date_string):
    try:
        return datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        raise argparse.ArgumentTypeError("Invalid date format. Use: yyyy-mm-ddThh:mm:ss")
    
def is_date_in_range(date_string, date_before, date_after):
    try:
        bunkr_date = datetime.strptime(date_string, '%H:%M:%S %d/%m/%Y')
        date_before = datetime.max if date_before is None else date_before
        date_after = datetime.min if date_after is None else date_after

        return bunkr_date <= date_before and bunkr_date >= date_after

    except ValueError:
        print(f"\t[-] Invalid file date {date_string}")
        return False
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(sys.argv[1:])
    parser.add_argument("-u", help="Url to fetch", type=str, required=False, default=None)
    parser.add_argument("-f", help="File to list of URLs to download", required=False, type=str, default=None)
    parser.add_argument("-r", help="Amount of retries in case the connection fails", type=int, required=False, default=10)
    parser.add_argument("-e", help="Extensions to download (comma separated)", type=str)
    parser.add_argument("-p", help="Path to custom downloads folder")
    parser.add_argument("-w", help="Export url list (ex: for wget)", action="store_true")
    parser.add_argument("--before", help="Export only files before this date", type=date_argument, default=None)
    parser.add_argument("--after", help="Export only files after this date", type=date_argument, default=None)

    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')

    if args.u is None and args.f is None:
        print("[-] No URL or file provided")
        sys.exit(1)

    if args.u is not None and args.f is not None:
        print("[-] Please provide only one URL or file")
        sys.exit(1)

    session = create_session()

    MAX_RETRIES = args.r

    if args.f is not None:
        with open(args.f, 'r', encoding='utf-8') as f:
            urls = f.read().splitlines()
        for url in urls:
            print(f"\t[-] Processing \"{url}\"...")
            get_items_list(session, url, args.e, args.w, args.p, date_before=args.before, date_after=args.after)
        sys.exit(0)
    else:
        get_items_list(session, args.u, args.e, args.w, args.p, date_before=args.before, date_after=args.after)
        
    sys.exit(0)
