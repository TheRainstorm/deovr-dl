from datetime import datetime
import threading
import queue
import os
import time
import requests
import argparse
import re
import json
import re
from donwloader import seconds_to_hms, download_file, download_file_in_chunks

def parseCookieFile(cookie_file) -> dict:
    ''' parseCookieFile function used to convert
        NetScape cookies file into a dictionary '''
    # https://gist.github.com/h3ssan/28196d1b4361b96b9358e844e5bb5cf0
    
    cookies = {}
    with open (cookie_file) as file:
        for line in file:
            if not re.match(r'^\#', line):
                lineFields = line.strip().split('\t')
                try:
                    cookies[lineFields[5]] = lineFields[6]
                except IndexError:
                    pass
    
    return cookies

def sanitize_filename(filename):
    # windows forbidden characters
    forbidden_chars = r'[\\/:"*?<>|]'
    sanitized = re.sub(forbidden_chars, ' ', filename)
    return sanitized

def parse_web(url):
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }
    response = session.get(url, headers=headers)

    # extract videoData object
    match = re.search(r'videoData\s*:\s*(.*),\n', response.text)
    if not match:
        print('videoData parsing failed')
        return False, None

    video_data_json = match.group(1)
    video_data = json.loads(video_data_json)
    # print(json.dumps(video_data, indent=4))
    
    json_url = f"https://deovr.com/deovr/video/id/{video_data['id']}"
    video_json = session.get(json_url, headers=headers).json()

    return True, video_json

def print_metadata(video_json):
    print(f"**** Parsed data:")
    print(f"** Title: {video_json['title']}")
    print(f"** Id: {video_json['id']}")
    upload_date = datetime.fromtimestamp(video_json['date']).strftime('%Y-%m-%d %H:%M:%S')
    print(f"** Date: {upload_date}")
    print(f"** Description: {video_json['description']}")
    
    print(f"\n** Angle: {video_json['viewAngle']}")
    print(f"** 3D Format: {video_json['stereoMode']}")
    print(f"** screenType: {video_json['screenType']}")
    print(f"** Duration: {seconds_to_hms(video_json['videoLength'])}")
    
    
    print(f"\n** Views: {video_json['quantity']['views']}")
    print(f"** Comments: {video_json['quantity']['comments']}")
    print(f"** Favorites: {video_json['quantity']['favorites']}")
    print(f"** isPremium: {video_json['isPremium']}")

def get_src_list(video_json):
    ''' get url list from video_json with need info
    '''
    src_list = []
    for e in video_json['encodings']:
        srcs = e['videoSources']
        if len(srcs) == 0:
            continue
        for s in srcs:
            src = {}
            src['encoding'] = e['name']
            src['url'] = s['url']
            src['quality'] = f"{s['resolution']}p"
            src['height'] = s['height']
            src['width'] = s['width']
            src_list.append(src)
    
    # sort by quality
    src_list.sort(key=lambda x: int(x['quality'][:-1]))
    return src_list
    
def print_formats(src_list):
    print("\n**** Available formats:")
    for i, s in enumerate(src_list):
        print(f"{i}: \t{s['quality']} \t{s['width']:>5d}x{s['height']:<5d} \t{s['encoding']}")

def select_format(src_list, encodings=['h264'], select_format_idx=-1):
    if args.select_format_idx != -1:
        return src_list[select_format_idx]
    filter_src = [src for src in src_list if src['encoding'] in encodings]
    return filter_src[-1]  # best quality in filtered encoding

parser = argparse.ArgumentParser(description='Download url from deovr')
parser.add_argument('-u', '--url', help='URL of video page')
parser.add_argument('-O', '--output-dir', default='./', help='Output file dir')
parser.add_argument('-t', '--title', default='', help='Used to construct filename. If not set, parse title from web')
parser.add_argument('-y', '--overwrite', action="store_true", help='overwrite exist')
parser.add_argument('-C', '--cookie-file', default='', help='cookie file')
# format select
parser.add_argument('-F', '--list-format', action="store_true", help='list all available format')
parser.add_argument('-c', '--encoding', nargs='+', default='h264', help='filter selected encoding. e.g -c h264 h265, default only h264')
parser.add_argument('-f', '--select-format-idx', type=int, default=-1, help='select format by index. If not set, select the best quality with filted encoding')

parser.add_argument('-n', '--thread-number', type=int, default=0, help='parallel download threads, 0 for original downloader')
parser.add_argument('-S', '--chunk-size', type=int,  default=20*1024**2, help='Download in chunks of n bytes, default 20 MiB')
args = parser.parse_args()

cookies = {}
if args.cookie_file:
    cookies = parseCookieFile(args.cookie_file)
session = requests.Session()
session.cookies.update(cookies)

# get single video json
success, video_json = parse_web(args.url)
if not success:
    print('Failed to parse web')
    exit(-1)

# print metadata
print_metadata(video_json)

# format select
src_list = get_src_list(video_json)
if args.list_format:
    print_formats(src_list)
    exit(0)
selected_src = select_format(src_list, encodings=args.encoding, select_format_idx=args.select_format_idx)

# print selected
print(f"\n**** Download Param:")
print(f"** Select encoding: {selected_src['encoding']}")
print(f"** Selected quality: {selected_src['quality']}")
if args.thread_number!=0:
    print(f"** Chunk size {args.chunk_size/1024**2:.2f} MiB")
    print(f"** Threads: {args.thread_number}")

# download url
if not args.title:
    args.title = sanitize_filename(video_json['title'])

if not os.path.exists(args.output_dir):
    os.makedirs(args.output_dir, exist_ok=True)
filename = f"{args.title} - {selected_src['encoding']} {selected_src['quality']}"
output_file = os.path.join(args.output_dir, f"{filename}.mp4")
output_tmp_file = os.path.join(args.output_dir, f"{filename}.mp4.tmp")
recover_file = os.path.join(args.output_dir, f"{filename}.recover.json")

print(f"Download to: {output_file}")
if os.path.exists(output_file):
    print('File already exists')
    if not args.overwrite:
        print('Add -y to overwrite. \nExit')
        exit(0)

if args.thread_number == 0:
    download_file(session, selected_src['url'], output_file)
else:
    success = download_file_in_chunks(session, selected_src['url'], output_file=output_tmp_file, recover_file=recover_file, max_threads=args.thread_number, chunk_size=args.chunk_size)
    if success:
        print('Download successed')
        os.rename(output_tmp_file, output_file)
        print(f"File size: {os.path.getsize(output_file):,} bytes")
    else:
        print('Download failed, run again to recover')
