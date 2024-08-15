from datetime import datetime
import urllib.parse
import os
from lxml import html
import requests
import argparse
import re
import json
import re
from donwloader import sanitize_filename, seconds_to_hms, download_file, download_file_in_chunks
from compatibility import get_video_data, get_video_json_from_videoData

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

def make_dirs(*dirs, exist_ok=False):
    for d in dirs:
        os.makedirs(d, exist_ok=exist_ok)

class DeoVR_DL:
    def __init__(self):
        pass
    
    def parse_args(self):
        parser = argparse.ArgumentParser(description='Download url from deovr')
        parser.add_argument('-u', '--url', help='URL of video page')
        parser.add_argument('-O', '--output-dir', default='./', help='Output file dir')
        parser.add_argument('-t', '--title', default='', help='Used to construct filename. If not set, parse title from web')
        parser.add_argument('-y', '--overwrite', action="store_true", help='overwrite exist')
        parser.add_argument('-C', '--cookie-file', default='', help='cookie file')
        # format select
        parser.add_argument('-F', '--list-format', action="store_true", help='list all available format')
        parser.add_argument('-A', '--ask-for-download', action="store_true", help='ask for download before download video')
        parser.add_argument('-c', '--encoding', nargs='+', default='h265', help='filter selected encoding. e.g -c h264 h265, default only h265')
        parser.add_argument('-f', '--select-format-idx', type=int, default=-1, help='select format by index. If not set, select the best quality with filted encoding')
        parser.add_argument('-L', '--skip-policy', type=int, default=0, help="0: same res and encoding, 1: same encoding, 2: same title (diff encoding & res)")

        parser.add_argument('-n', '--thread-number', type=int, default=0, help='parallel download threads, 0 for original downloader')
        parser.add_argument('-K', '--chunk-size', type=int,  default=20*1024**2, help='Download in chunks of n bytes, default 20 MiB')
        parser.add_argument('-R', '--failed-repeat', type=int,  default=1, help='download failed repeat times')
        
        # hosting mode
        parser.add_argument('-H', '--hosting-mode', action="store_true", help='normal mode: download single video. Hosting mode: download and organize')
        parser.add_argument('-P', '--playlist', default="Library", help='playlist name, default `Library`. If the url is a playlist, the parsed playlist name will be used')
        parser.add_argument('-S', '--server', default="http://localhost:8000", help='HTTP server address hosting the video files')
        
        parser.add_argument('-E', '--force-metadata', action="store_true", help='force download missed metadata, don\'t download video')
        args = parser.parse_args()
        return args
    
    def process_args(self, args):
        self.args = args
        
        self.output_dir = args.output_dir
        if not os.path.exists(args.output_dir):
            os.makedirs(args.output_dir, exist_ok=True)

        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
        }
        cookies = {}
        if args.cookie_file:
            cookies = parseCookieFile(args.cookie_file)
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.session.cookies.update(cookies)
        
        if args.server.endswith('/'):
            self.server = args.server[:-1]
        else:
            self.server = args.server
    
    def run(self):
        args = self.parse_args()
        
        self.process_args(args)
        self.read_top_json()
        
        type, json_data = self.parse_url(self.args.url)
        if type == -1 :
            print('Failed to parse url')
            exit(-1)
        elif type == 1:
            print('Download Single video')
            self.download_single_video(json_data)
        else:
            print('Download Playlist')
            page_num = json_data['page_num']
            web_support = True
            for page in range(1, page_num):
                print(f"\nDownloading page {page}/{page_num}")
                if page == 1:
                    videos = json_data['page_1']
                else:
                    videos = self.parse_one_page(self.args.url, page)
                
                for i, video in enumerate(videos):
                    video_id, video_href = video
                    print(f"\nDownloading video {i+1}/{len(videos)}")
                    
                    if web_support:
                        code, video_json = self.get_video_json_from_id(video_id)
                        if code==1:
                            web_support = False
                            video_json = self.get_video_json_from_href(video_href)
                        elif code==2: # dirty fix, for some video, video json get empty url, but videoData contain url
                            video_json_tmp = self.get_video_json_from_href(video_href)
                            if video_json_tmp and video_json_tmp['encodings']:
                                video_json['encodings'] = video_json_tmp['encodings']
                    else:
                        video_json = self.get_video_json_from_href(video_href)
                        
                    self.download_single_video(video_json)
       
    def parse_url(self, url):
        response = self.session.get(url)
        with open('test.html', 'w') as f:
            f.write(response.text)

        # try single
        def try_single():
            video_data = get_video_data(response)
            if not video_data:
                return False, None
            # print(json.dumps(video_data, indent=4))
            
            code, video_json = self.get_video_json_from_id(video_data['id'])
            if code == 1:
                video_json = get_video_json_from_videoData(video_data)
            elif code == 2: # dirty fix, for some video, video json get empty url, but videoData contain url
                video_json_tmp = get_video_json_from_videoData(video_data)
                if video_json_tmp and video_json_tmp['encodings']:
                    video_json['encodings'] = video_json_tmp['encodings']
                    return True, video_json
            return True, video_json
        
        def try_playlist():
            tree = html.fromstring(response.text)
            page_num = tree.xpath('//*[@id="content"]//div[contains(@class, "c-pagination")]//ul/li[last()]/a/text()')
            if len(page_num) == 0:
                return False, None
            # playlist page
            page_num = int(page_num[0])
            
            videos = self.parse_one_page(url, 1, response)
            
            parsed_data = {
                'page_num': page_num,
                'page_1': videos
            }
            
            return True, parsed_data

        succ, json_data = try_single()
        if succ:
            return 1, json_data
        succ, json_data = try_playlist()
        if succ:
            return 2, json_data
        return -1, None
    
    def get_video_json_from_id(self, video_id):
        domain = self.args.url.split('/')[2]
        url = f"https://{domain}/deovr/video/id/{video_id}"
        video_json =  self.session.get(url).json()
        if "encodings" not in video_json:
            print(f"[Warnning]: {domain} don't support get json from video id. {video_json}")
            return 1, None
        if len(self.get_src_list(video_json))==0:
            print(f"[Warnning]: Empty video url")
            return 2, video_json
        return 0, video_json
    
    def get_video_json_from_href(self, href):
        domain = self.args.url.split('/')[2]
        url = f"https://{domain}{href}"
        response = self.session.get(url)
        video_data = get_video_data(response)
        return get_video_json_from_videoData(video_data)
    
    def parse_one_page(self, url, page, response=None):
        if response is None:
            response = self.session.get(url, params={'page': page})
        tree = html.fromstring(response.content)
        
        links_with_data_like_id = tree.xpath('//a[@data-like-id]')

        videos = [(link.get('data-like-id'), link.get('href')) for link in links_with_data_like_id]
        return videos
            
    def print_metadata(self, video_json):
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
        
        try:
            print(f"\n** Views: {video_json['quantity']['views']}")
            print(f"** Comments: {video_json['quantity']['comments']}")
            print(f"** Favorites: {video_json['quantity']['favorites']}")
            print(f"** isPremium: {video_json['isPremium']}")
        except:
            pass
        print(f"********\n")
    
    def get_src_list(self, video_json):
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
                if not s['url']:
                    continue
                src['url'] = s['url']
                src['resolution'] = s['resolution']
                src['quality'] = f"{s['resolution']}p"
                src['height'] = s['height']
                src['width'] = s['width']
                src_list.append(src)
        
        # sort by quality
        src_list.sort(key=lambda x: int(x['quality'][:-1]))
        return src_list
        
    def print_formats(self, src_list):
        print("\n**** Available formats:")
        for i, s in enumerate(src_list):
            print(f"{i}: \t{s['quality']} \t{s['width']:>5d}x{s['height']:<5d} \t{s['encoding']}")

    def select_format(self, src_list, encodings=['h264'], select_format_idx=-1):
        if len(src_list) == 0:
            return {}
        if self.args.select_format_idx != -1:
            return src_list[select_format_idx]
        filter_src = [src for src in src_list if src['encoding'] in encodings]
        selected_src = filter_src[-1] # best quality in filtered encoding

        return selected_src

    def download_single_video(self, video_json):
        if not video_json:
            print('Empty video json, skip')
            return
        # print metadata
        self.print_metadata(video_json)
        
        # title_id as identifier
        video_title_id = f"{sanitize_filename(video_json['title'])} [{video_json['id']}]"
        if self.args.title:
            video_title_id = self.args.title
        
        # format select
        src_list = self.get_src_list(video_json)
        if self.args.list_format:
            self.print_formats(src_list)
            exit(0)
        if len(src_list) == 0:
            print('No available format, skip')
            if not self.args.force_metadata:
                return
        
        selected_src = self.select_format(src_list, encodings=self.args.encoding, select_format_idx=self.args.select_format_idx)
        
        if not self.args.hosting_mode: # just download video
            self.download_video(video_title_id, self.output_dir, selected_src)
            return
        
        # hosting mode
        dump_json = video_json.copy()
        dump_json['title'] = video_title_id
        dump_json['id'] = self.get_current_id()
        dump_json['ext'] = '.mp4'
        del dump_json['encodings']
    
        # prepare dir
        playlist = self.args.playlist
        playlist_dir = os.path.join(self.output_dir, playlist)

        thumbnail_dir = os.path.join(playlist_dir, 'metadata', 'thumbnail')
        preview_dir = os.path.join(playlist_dir, 'metadata', 'preview')
        seeklookup_dir = os.path.join(playlist_dir, 'metadata', 'seeklookup')
        json_dir = os.path.join(playlist_dir, 'metadata', 'json')
        make_dirs(thumbnail_dir, preview_dir, seeklookup_dir, json_dir, exist_ok=True)
        
        single_json_data = {}
        single_json_path = os.path.join(json_dir, f'{video_title_id}.json')
        if os.path.exists(single_json_path):
            with open(single_json_path, 'r') as f:
                single_json_data = json.load(f)
        if 'encodings' not in single_json_data:
            single_json_data['encodings'] = []
        
        if not self.args.force_metadata:
            # check exist skip
            exist_flag = self.add_encoding(single_json_data['encodings'].copy(), selected_src.copy())
            if exist_flag <= self.args.skip_policy:
                print(f'Skip this video. exist_flag={exist_flag}, skip_policy={self.args.skip_policy}')
                return
        
            # download video
            video_path, succ = self.download_video(video_title_id, playlist_dir, selected_src)
            if not succ:
                print(f"Download video failed, skip")
                return

            # modify url
            url_path = urllib.parse.quote(os.path.relpath(video_path, self.output_dir))
            selected_src['url'] = f"{self.server}/{url_path}"
            
            self.add_encoding(single_json_data['encodings'], selected_src)
        
        # download metadata (after video download, if we don't download video, we don't need metadata)
        print("Downloading metadata")
        self.download_others(video_json, dump_json, video_title_id, thumbnail_dir, preview_dir, seeklookup_dir)
        
        # self extended key, top playlist json will use it
        # url_path = urllib.parse.quote(f"{playlist}/metadata/json/{video_title_id}.json")
        # dump_json['video_url'] = f"{self.server}/{url_path}"
        dump_json['video_url'] = f"{self.server}/{playlist}/metadata/json/{video_title_id}.json"  # test, it's ok
        single_json_data.update(dump_json)
        
        # save json
        print("Save single video json")
        with open(single_json_path, 'w') as f:
            json.dump(single_json_data, f, indent=4)
        
        # add to top.json
        print("Add to top json")
        self.add_to_top_json(playlist, single_json_data, video_title_id)
       
    def download_video(self, video_title_id, output_dir, selected_src):
        succ = True
        filename = f"{video_title_id} - {selected_src['encoding']} {selected_src['quality']}"
        output_file = os.path.join(output_dir, f"{filename}.mp4")
        output_tmp_file = os.path.join(output_dir, f"{filename}.mp4.tmp")
        recover_file = os.path.join(output_dir, f"{filename}.recover.json")
        
        # print selected
        print(f"Downloading Video:")
        print(f"** Select encoding: {selected_src['encoding']}")
        print(f"** Selected quality: {selected_src['quality']}")
        print(f"** Save to: {output_file}")
        if self.args.thread_number!=0:
            print(f"** Chunk size {self.args.chunk_size/1024**2:.2f} MiB")
            print(f"** Threads: {self.args.thread_number}")
        
        if os.path.exists(output_file):
            if self.args.overwrite:
                os.remove(output_file)
            else:
                print(f"Video file exists, skip")
                return output_file, succ
        if self.args.ask_for_download:
            ans = input('Continue? [y/n]: ')
            if ans.lower() != 'y':
                print('Skip')
                return output_file, False
        
        if self.args.thread_number == 0:
            succ = download_file(self.session, selected_src['url'], output_file, print_info=True, repeat=self.args.failed_repeat)
        else:
            succ = download_file_in_chunks(self.session, selected_src['url'], output_file=output_tmp_file, recover_file=recover_file, \
                max_threads=self.args.thread_number, chunk_size=self.args.chunk_size, repeat=self.args.failed_repeat)
            if succ:
                print('Download successed')
                os.rename(output_tmp_file, output_file)
                print(f"File size: {os.path.getsize(output_file):,} bytes")
            else:
                print('Download failed, run again to recover')
        return output_file, succ
    
    def download_others(self, video_json, dump_json, video_title_id, thumbnail_dir, preview_dir, seeklookup_dir):
        repeat = self.args.failed_repeat
        # The field ‘thumbnailUrl’ should contain the link to the file with the image shown in the list. This field is required in case of using the list.
        output_path = os.path.join(thumbnail_dir, f"{video_title_id}_thumbnail.jpg")
        if not os.path.exists(output_path):
            download_file(self.session, video_json['thumbnailUrl'], output_path, repeat=repeat)
        url_path = urllib.parse.quote(os.path.relpath(output_path, self.output_dir))
        dump_json['thumbnailUrl'] = f"{self.server}/{url_path}"
        
        # (optional) The field ‘videoPreview’ contains the link to the video file, which is shown when moving the cursor to this video in the list. This field is not required.
        if 'videoPreview' in video_json:
            output_path = os.path.join(preview_dir, f"{video_title_id}_preview.mp4")
            if not os.path.exists(output_path):
                download_file(self.session, video_json['videoPreview'], output_path, repeat=repeat)
            url_path = urllib.parse.quote(os.path.relpath(output_path, self.output_dir))
            dump_json['videoPreview'] = f"{self.server}/{url_path}"
        
        # (optional) You can add a video file which will be used to show the rewind of the file in the player.
        if 'videoThumbnail' in video_json:
            # !!! obsolescent, not used
            # output_path = os.path.join(seeklookup_dir, f"{video_title_id}_seek.mp4")
            # if not os.path.exists(output_path):
            #     download_file(self.session, video_json['videoThumbnail'], output_path, repeat=repeat)
            # url_path = urllib.parse.quote(os.path.relpath(output_path, self.output_dir))
            # dump_json['videoThumbnail'] =f"{self.server}/{url_path}"
            dump_json['videoThumbnail'] = ""
        
        if 'timelinePreview' in video_json:
            output_path = os.path.join(seeklookup_dir, f"{video_title_id}_timelinePreview.jpg")
            if not os.path.exists(output_path):
                download_file(self.session, video_json['timelinePreview'], output_path, repeat=repeat)
            url_path = urllib.parse.quote(os.path.relpath(output_path, self.output_dir))
            dump_json['timelinePreview'] =f"{self.server}/{url_path}"

    def add_encoding(self, encodings, selected_src):
        exist_flag = 2
        if len(encodings) == 0:
            exist_flag = 3 # not exist same title video
        for e in encodings:
            if e['name'] == selected_src['encoding']:
                for s in e['videoSources']:
                    if s['resolution'] == selected_src['resolution']:
                        return 0 # already exists
                e['videoSources'].append({
                    'url': selected_src['url'],
                    'resolution': selected_src['resolution'],
                    'height': selected_src['height'],
                    'width': selected_src['width']
                })
                return 1 # same encoding, new resolution
        encodings.append({
            'name': selected_src['encoding'],
            'videoSources': [{
                'url': selected_src['url'],
                'resolution': selected_src['resolution'],
                'height': selected_src['height'],
                'width': selected_src['width']
            }]
        })
        return exist_flag # new encoding
    
    def read_top_json(self):
        # read playlist json
        top_json_path = os.path.join(self.output_dir, 'top.json')
        self.top_json = {'scenes': []}
        if os.path.exists(top_json_path):
            with open(top_json_path, 'r') as f:
                self.top_json = json.load(f)
        
    def get_current_id(self):
        # # current id
        # video_num = 0
        # for scene in self.top_json['scenes']:
        #     video_num += len(scene['list'])
        # return video_num
        return self.top_json['current_id']
    
    def write_top_json(self):
        top_json_path = os.path.join(self.output_dir, 'top.json')
        with open(top_json_path, 'w') as f:
            json.dump(self.top_json, f, indent=4)
        
        alias_json_path = os.path.join(self.output_dir, 'deovr')
        if not os.path.exists(alias_json_path):
            os.symlink(top_json_path, alias_json_path)
    
    def add_to_top_json(self, playlist, single_json, video_title_id):
        short_single_json = {
            'title': single_json['title'],
            'vidoeLength': single_json['videoLength'],
            'video_url': single_json['video_url'],
            'thumbnail_url': single_json['thumbnailUrl'],
        }
        self.read_top_json()
        same_playlist = False
        for scene in self.top_json['scenes']:
            if scene['name'] == playlist:
                for video in scene['list']:
                    if video['title'] == single_json['title']:
                        return
                same_playlist = True
                scene['list'].append(short_single_json)
                break
        if not same_playlist:
            # add playlist
            self.top_json['scenes'].append({
                'name': playlist,
                'list': [short_single_json]
            })
        
        self.top_json['current_id'] += 1
        self.write_top_json()

if __name__ == '__main__':
    downloader = DeoVR_DL()
    downloader.run()
