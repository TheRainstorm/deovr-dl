import threading
import queue
import os
import requests
import argparse
from bs4 import BeautifulSoup
import re
import json

def sanitize_filename(filename):
    # windows forbidden characters
    forbidden_chars = r'[\\/:"*?<>|]'
    sanitized = re.sub(forbidden_chars, ' ', filename)
    return sanitized

def parse_web(url):
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }
    response = requests.get(url, headers=headers)
    
    soup = BeautifulSoup(response.text, 'lxml')

    script_tags = soup.find_all('script', type='text/javascript')
    
    # find script contains videoData
    video_data_script = None
    for script in script_tags:
        if 'videoData' in script.string:
            video_data_script = script.string
            break
    
    if not video_data_script:
        print('No script tag with videoData found')
        return False, None

    # extract videoData object
    match = re.search(r'videoData\s*:\s*(.*),\n', video_data_script)
    if not match:
        print('videoData parsing failed')
        return False, None

    video_data_json = match.group(1)
    video_data = json.loads(video_data_json)
    # print(json.dumps(video_data, indent=4))
    
    parsed_data = {
        'title': video_data['title'],
        'src': video_data['src'],
    }
    return True,parsed_data

def download_chunk(tid, result_queue, shared_data, lock):
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }
    
    while True:
        with lock:
            start = shared_data['start']
            total_size = shared_data['total_size']
            if start >= total_size:
                break
            shared_data['start'] += shared_data['chunk_size']
        end = start + shared_data['chunk_size'] - 1
        print(f"Thread {tid}: Downloading bytes {start:,}-{end:,}")
        
        chunk_headers = headers.copy()
        chunk_headers['Range'] = f'bytes={start}-{end}'
        response = requests.get(shared_data['url'], headers=chunk_headers, stream=True)

        if response.status_code == 206:
            result_queue.put((tid, start, response.content))
        elif response.status_code == 416:
            with lock:
                shared_data['total_size'] = min(shared_data['total_size'], end+1)  # set temp total size, true size is smaller
            # retry
            chunk_headers['Range'] = f'bytes={start}-'
            response = requests.get(shared_data['url'], headers=chunk_headers, stream=True)
            end = start + len(response.content) - 1
            if start >= end: # still 416, start is too big
                break
            with lock:
                shared_data['total_size'] = min(shared_data['total_size'], end+1)  # set temp total size, true size is smaller
            result_queue.put((tid, start, response.content))
            print(f"Thread {tid}: 416, downloaded bytes {start:,}-{end:,}")
            break
        else:
            print(f'{tid} Error: HTTP response code {response.status_code}')
            exit(-1)
    result_queue.put((tid, -1, None))
    print(f'Thread {tid} finished')

def download_file_in_chunks(url, start_offset=0, chunk_size=100 * 1024 * 1024, output_file='output.mp4', max_threads=4):
    shared_data = {
        'url': url,
        'chunk_size': chunk_size,
        'start': 0,
        'total_size': 1024**5,  # big enough size
    }
    
    lock = threading.Lock()

    result_queue = queue.Queue()
    for i in range(max_threads):
        t = threading.Thread(target=download_chunk, args=(i, result_queue, shared_data, lock))
        t.start()
    
    count_finished = 0
    with open(output_file, 'wb') as f:
        while True:
            tid, start, chunk = result_queue.get()
            if start == -1:
                count_finished += 1
                if count_finished == max_threads:
                    break
                continue
            # print(f'Thread {tid}: Downloaded bytes {start}-{start + len(chunk) - 1}')
            f.seek(start)
            f.write(chunk)
    print(f"Download completed: {shared_data['total_size']:,}|{shared_data['total_size']/1024**2:.2f} MiB")

parser = argparse.ArgumentParser(description='Download url from deovr')
parser.add_argument('-u', '--url', help='URL of video page')
parser.add_argument('-O', '--output-dir', default='./', help='Output file dir')
parser.add_argument('-t', '--title', default='', help='Used to construct filename. If not set, parse title from web')

parser.add_argument('-n', '--thread-number', type=int, default=6, help='parallel download threads, default 6')
parser.add_argument('-c', '--code', default='h264', help='Select video codec, e.g h264, h265')

parser.add_argument('-C', '--chunck-size', type=int,  default=25*1024**2, help='Download in chunks of n bytes, default 25 MiB')
# parser.add_argument('-S', '--start-offset', type=int, help='download skip the first n bytes', default=0)
args = parser.parse_args()

success, parsed_data = parse_web(args.url)
if not success:
    print('Failed to parse web')
    exit(-1)
print(f"Title: {parsed_data['title']}")

# get url
filter_url = []
for i,src in enumerate(parsed_data['src']):
    if src['encoding'] == args.code:
        filter_url.append((src['url'], src['quality']))

filter_url.sort(key=lambda x: x[1], reverse=True)

selected_url, selected_quality = filter_url[0]
print(f"Selected quality: {selected_quality}")

# download url
if not args.title:
    args.title = sanitize_filename(parsed_data['title'])

if not os.path.exists(args.output_dir):
    os.makedirs(args.output_dir, exist_ok=True)
output_file = os.path.join(args.output_dir, args.title + '.mp4')

print(f"Download to: {output_file}")
if os.path.exists(output_file):
    print('File already exists')
    overwrite = input('Do you want to overwrite it? (y/n): ')
    if overwrite.lower() != 'y':
        print('Download aborted')
        exit(0)
    
download_file_in_chunks(selected_url, output_file=output_file, chunk_size=args.chunck_size, max_threads=args.thread_number)
