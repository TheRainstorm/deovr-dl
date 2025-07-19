from datetime import datetime
import urllib.parse
import os
from lxml import html
import requests
import argparse
import re
import json
from donwloader import sanitize_filename, seconds_to_hms, download_file, download_file_in_chunks
from compatibility import get_video_data, get_video_json_from_videoData
from db_utils import *

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

class DeoVR_DL:
    def __init__(self):
        pass
    
    def get(self, url, **kwargs):
        repeat = self.args.failed_repeat
        while repeat>0:
            try:
                response = self.session.get(url, **kwargs)
                return response
            except Exception as e:
                repeat -= 1
                if repeat == 0:
                    print(f"Get {url} failed {self.args.failed_repeat} times, exit")
                    print(f"Exception: {e}")
                    exit(-1)
    
    def parse_args(self):
        parser = argparse.ArgumentParser(description='Download url from deovr')
        parser.add_argument('-u', '--url', help='URL of video page')
        parser.add_argument('-O', '--root-dir', default='./', help='deovr root dir')
        parser.add_argument('-t', '--title', default='', help='Used to construct filename. If not set, parse title from web')
        parser.add_argument('-y', '--overwrite', action="store_true", help='overwrite exist')
        parser.add_argument('-C', '--cookie-file', default='', help='cookie file')
        # format select
        parser.add_argument('-F', '--list-format', action="store_true", help='list all available format')
        parser.add_argument('-A', '--ask-for-download', action="store_true", help='ask for download before download video')
        parser.add_argument('-c', '--encodings', nargs='+', default=['h265', 'av1', 'h264'], help='filter selected encoding. e.g -c h264 h265, default only h265. Moreover, The order defines the priority of encoding')
        parser.add_argument('-q', '--max-quality', type=int, default=-1, help='filter selected quality. e.g pico4/ultra only support 4096p. default -1, no filter')
        parser.add_argument('--also-download-best-quality', action='store_true', help='also download the best quality video, even if it is not in the supported quality')
        parser.add_argument('-f', '--select-format-idx', type=int, default=-1, help='select format by index. If not set, select the best quality with filted encoding')
        parser.add_argument('-L', '--skip-policy', type=int, default=0, help="0: same res and encoding, 1: same encoding, 2: same title (diff encoding & res)")

        parser.add_argument('-n', '--thread-number', type=int, default=0, help='parallel download threads, 0 for original downloader')
        parser.add_argument('-K', '--chunk-size', type=int,  default=20*1024**2, help='Download in chunks of n bytes, default 20 MiB')
        parser.add_argument('-R', '--failed-repeat', type=int,  default=3, help='download failed repeat times')
        
        # hosting mode
        parser.add_argument('-H', '--hosting-mode', action="store_true", help='normal mode: download single video. Hosting mode: download and organize')
        parser.add_argument('-P', '--playlist', default="Library", help='playlist name, default `Library`. If the url is a playlist, the parsed playlist name will be used')
        parser.add_argument('-p', '--playlist-range', default=":", help='playlist start:end range. ":1", "-1:"')
        parser.add_argument('-S', '--server', default="http://localhost:8000", help='HTTP server address hosting the video files')
        
        parser.add_argument('-E', '--force-metadata', action="store_true", help='force download missed metadata, don\'t download video')
        args = parser.parse_args()
        return args
    
    def process_args(self, args):
        self.args = args
        
        self.root_dir = args.root_dir
        if not os.path.exists(args.root_dir):
            os.makedirs(args.root_dir, exist_ok=True)

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
            
            start_page, end_page = self.args.playlist_range.split(':')
            start_page = 1 if start_page=='' else int(start_page)
            end_page = page_num if end_page=='' else int(end_page)
            if start_page < 0:
                start_page += page_num + 1
            if end_page < 0:
                end_page += page_num + 1
            print(f"download range: {start_page}:{end_page}")
            for page in range(start_page, end_page + 1):
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
                    
                    # with open('current.json', 'w') as f:
                    #     json.dump(video_json, f, indent=4)
                    self.download_single_video(video_json)
       
    def parse_url(self, url):
        response = self.get(url)
        # with open('test.html', 'w') as f:
        #     f.write(response.text)

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
        video_json =  self.get(url).json()
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
        response = self.get(url)
        video_data = get_video_data(response)
        return get_video_json_from_videoData(video_data)
    
    def parse_one_page(self, url, page, response=None):
        if response is None:
            response = self.get(url, params={'page': page})
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

    def select_formats(self, src_list):
        if len(src_list) == 0:
            return []
        if self.args.select_format_idx != -1:
            return [src_list[self.args.select_format_idx]]
        
        filter_src = [src for src in src_list if src['encoding'] in self.args.encodings]
        # sort by quality then encoding priority
        filter_src.sort(key=lambda x: (int(x['quality'][:-1]), -self.args.encodings.index(x['encoding']) if x['encoding'] in self.args.encodings else -len(self.args.encodings)))
        # self.print_formats(filter_src)
        best_src = filter_src[-1]
        if self.args.max_quality > 0:
            filter_src = [src for src in filter_src if int(src['quality'][:-1]) <= self.args.max_quality]
        best2_src = filter_src[-1]
        if best_src != best2_src and self.args.also_download_best_quality:
            print(f"Also download the best quality: {best_src['quality']}")
            return [best_src, best2_src]
        return [best2_src]

    def download_single_video(self, video_json):
        if not video_json:
            print('Empty video json, skip')
            return
        # print metadata
        self.print_metadata(video_json)
        
        # title_id as identifier
        title = f"{sanitize_filename(video_json['title'])} [{video_json['id']}]"
        if self.args.title:
            title = self.args.title
        
        # format select
        src_list = self.get_src_list(video_json)
        if self.args.list_format:
            self.print_formats(src_list)
            exit(0)
        if len(src_list) == 0:
            print('No available format, skip')
            if not self.args.force_metadata:
                return
        
        selected_srcs = self.select_formats(src_list)
        
        if not self.args.hosting_mode: # just download video
            for selected_src in selected_srcs:
                self.download_video(title, self.root_dir, selected_src)
            return

        for selected_src in selected_srcs:
            # hosting mode
            db_json = read_db_json(self.root_dir)
            dump_json = video_json.copy()
            dump_json['title'] = title
            dump_json['id'] = get_current_id(db_json)
            dump_json['ext'] = '.mp4'
            del dump_json['encodings']
        
            # prepare dir
            playlist = self.args.playlist
            playlist_dir = os.path.join(self.root_dir, playlist)

            thumbnail_dir = os.path.join(playlist_dir, 'metadata', 'thumbnail')
            preview_dir = os.path.join(playlist_dir, 'metadata', 'preview')
            seeklookup_dir = os.path.join(playlist_dir, 'metadata', 'seeklookup')
            json_dir = os.path.join(playlist_dir, 'metadata', 'json')
            make_dirs(thumbnail_dir, preview_dir, seeklookup_dir, json_dir, exist_ok=True)
            
            video_json_ori = read_video_json(self.root_dir, playlist, title)
            if 'encodings' not in video_json_ori:
                video_json_ori['encodings'] = []
            
            if not self.args.force_metadata:
                # check exist skip
                exist_flag = check_encoding(video_json_ori['encodings'], selected_src['encoding'], selected_src['resolution'])
                if exist_flag <= self.args.skip_policy:
                    print(f'Skip this video. exist_flag={exist_flag}, skip_policy={self.args.skip_policy}')
                    continue
            
                # download video
                video_path, succ = self.download_video(title, playlist_dir, selected_src)
                if not succ:
                    print(f"Download video failed, skip")
                    continue

                # modify url
                url_path = urllib.parse.quote(os.path.relpath(video_path, self.root_dir))
                selected_src['url'] = f"{self.server}/{url_path}"
                
                add_encoding(video_json_ori['encodings'], selected_src['encoding'],
                                self.get_videoSource(selected_src))
            
            # download metadata (after video download, if we don't download video, we don't need metadata)
            print("Downloading metadata")
            self.download_others(video_json, dump_json, title, thumbnail_dir, preview_dir, seeklookup_dir)
            
            # self extended key, top playlist json will use it
            dump_json['video_url'] = f"{self.server}/{playlist}/metadata/json/{title}.json"  # test, it's ok
            video_json_ori.update(dump_json)
            
            # save video json
            print("Save single video json")
            write_video_json(self.root_dir, playlist, title, video_json_ori)
            
            # add to db
            print("Add to top json")
            db_add_title(db_json, playlist, video_json_ori)
            write_db_json(self.root_dir, db_json)
       
    def download_video(self, title, output_dir, selected_src):
        succ = True
        filename = f"{title} - {selected_src['encoding']} {selected_src['quality']}"
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
    
    def download_others(self, video_json, dump_json, title, thumbnail_dir, preview_dir, seeklookup_dir):
        repeat = self.args.failed_repeat
        # The field ‘thumbnailUrl’ should contain the link to the file with the image shown in the list. This field is required in case of using the list.
        output_path = os.path.join(thumbnail_dir, f"{title}_thumbnail.jpg")
        if not os.path.exists(output_path):
            download_file(self.session, video_json['thumbnailUrl'], output_path, repeat=repeat)
        url_path = urllib.parse.quote(os.path.relpath(output_path, self.root_dir))
        dump_json['thumbnailUrl'] = f"{self.server}/{url_path}"
        
        # (optional) The field ‘videoPreview’ contains the link to the video file, which is shown when moving the cursor to this video in the list. This field is not required.
        if 'videoPreview' in video_json:
            output_path = os.path.join(preview_dir, f"{title}_preview.mp4")
            if not os.path.exists(output_path):
                download_file(self.session, video_json['videoPreview'], output_path, repeat=repeat)
            url_path = urllib.parse.quote(os.path.relpath(output_path, self.root_dir))
            dump_json['videoPreview'] = f"{self.server}/{url_path}"
        
        # (optional) You can add a video file which will be used to show the rewind of the file in the player.
        if 'videoThumbnail' in video_json:
            # !!! obsolescent, not used
            # output_path = os.path.join(seeklookup_dir, f"{title}_seek.mp4")
            # if not os.path.exists(output_path):
            #     download_file(self.session, video_json['videoThumbnail'], output_path, repeat=repeat)
            # url_path = urllib.parse.quote(os.path.relpath(output_path, self.root_dir))
            # dump_json['videoThumbnail'] =f"{self.server}/{url_path}"
            dump_json['videoThumbnail'] = ""
        
        if 'timelinePreview' in video_json:
            output_path = os.path.join(seeklookup_dir, f"{title}_4096_timelinePreview341x195.jpg")
            if not os.path.exists(output_path):
                download_file(self.session, video_json['timelinePreview'], output_path, repeat=repeat)
            url_path = urllib.parse.quote(os.path.relpath(output_path, self.root_dir))
            dump_json['timelinePreview'] =f"{self.server}/{url_path}"
    
    def get_videoSource(self, selected_src):
        return {
            'url': selected_src['url'],
            'resolution': selected_src['resolution'],
            'height': selected_src['height'],
            'width': selected_src['width']
        }

if __name__ == '__main__':
    downloader = DeoVR_DL()
    downloader.run()
