## Intro

[DeoVR](https://deovr.com/) is a great VR video streaming platform. It features a large amount of user-uploaded content, including many high-quality videos such as cosplay convention, various tech expos, travel vlogs, and more. The video resolution is also very high, with regular users able to watch single-eye 4160p videos for free. However, DeoVR does have a downside: videos that were previously available for free may become exclusive to members after some time. Therefore, for videos you really like, it's crucial to download them.

Currently, only members of DeoVR can download 3 videos per month. And the yt-dlp project does not yet support the DeoVR website.

To address the above issues, this script is used to download videos from DeoVR offline.

## Usage

### Install

```shell
conda create -n py10 python=3.10  # test on python 3.10
# or python3 -m venv .venv && source .venv/bin/activate

pip install -r requirements.txt
```

### Download single video

Support for deovr.com, jillvr.com, and others. Try it yourself.

```shell
python deovr-dl.py -u https://deovr.com/oraehm          # download best quality video
python deovr-dl.py -O ./output -u https://deovr.com/oraehm       # specify output dir
python deovr-dl.py -u https://deovr.com/oraehm -F       # list all available format
python deovr-dl.py -u https://deovr.com/oraehm -f 0     # select format by index
python deovr-dl.py -u https://deovr.com/oraehm -c h265     # download h265 best quality video
python deovr-dl.py -O ./output -u https://deovr.com/oraehm -n 6  # specify thread number
```

### Download playlist

Support most page using similar paginator, e.g. `https://deovr.com/user/favorites`, `https://deovr.com/playlists/xxx`

```shell
# download all video in playlist, script will download video one by one, page by page
python deovr-dl.py -O /path/to/deovr/root -C "/path/to/cookies.txt" -u https://deovr.com/user/favorites -P fav
python deovr-dl.py -O /path/to/deovr/root -C "/path/to/cookies.txt" -u https://deovr.com/user/favorites -P fav -p ":1"  # download first page. ":" (all page), "-1:" (last page)

# if your network is not good, you should use multiple thread downloading (which can recover from failed), 
# and set failed repeat time, decreasing chunk size (10M)
python -u deovr-dl.py -O /path/to/deovr/root -C "/path/to/cookies.txt" -u https://deovr.com/user/favorites -P fav -n 6 -R 100 -K 10485760 2>&1 | tee run.log
```

## Self-hosting Web Server

DeoVR provides [documentation](https://deovr.com/app/doc#multiple-videos-deeplink) on how to integrate DeoVR into your own website.

The key is to provide a JSON file that includes direct links to video files and other metadata. By opening the JSON link with the built-in browser in the DeoVR player, you can display and play all the videos.

Therefore, when downloading videos, we can save other metadata and generate a JSON file with url replaced by our server. Then, we can set up a HTTP server using `Nginx`. Finally, we can browse and play our videos in the DeoVR player.

The downloaded files will be organized as follow:

```shell
output_dir
├── playlist1
│   ├── metadata
|   │   ├── thumbnail  # preview image
|   │   |   ├── title_0.jpg
|   │   |   `── title_1.jpg
|   │   ├── preview    # preview video
|   │   ├── seeklookup
|   │   `── json
|   │   |   ├── title_0.json  # Single videos deeplink
|   │   |   `── title_1.json
│   ├── title_0.mp4
│   `── title_1.mp4
│
├── playlist2
├── top.json   # Multiple videos selection deeplink
`── deovr      # link to top.json, according to DeoVR default behavior
```

```shell
# download video and save to default playlist `Library`
python deovr-dl.py -O /path/to/deovr_root/ -H -S "https://example.com" -u https://deovr.com/xxx  # -H mean hosting mode

# download deovr favorite playlist, save as `fav`
python deovr-dl.py -O /path/to/deovr/root -C "/path/to/cookies.txt" -H -S "https://example.com" -u https://deovr.com/user/favorites -P fav
```

### nginx setup

```text
server {
        listen 443 ssl;
        listen [::]:443 ssl;
        server_name example.com;
        root    /path/to/deovr_root/;

        location / {
                autoindex on;
                try_files $uri $uri/ = 404;
        }
}
```

Open `https://example.com/` in DeoVR player then enjoy your videos.

If you change server address, please run script to rewrite json files.

```shell
python replace_server_name.py -T /path/to/deovr/root -S "https://old.example:4433" -R "https://new.example.com"
```

## Scan local video

Sometimes we want to host local VR videos. It's tedious to write JSON by ourselves, so there is a script to scan the directory and generate the correct JSON, which will also create thumbnail images and preview videos.

1. Place the directory (e.g., `foo`) containing local videos in the DeoVR root directory.
2. Run the script with the playlist name identical to the directory name (e.g., `foo`).

```shell
# scan video

# scan for new video in foo directory, and add to playlist
python generate_json.py -T /path/to/deovr/root -S "https://example.com" -P foo
# Scan for specific video, and using specific 3d format
python generate_json.py -T /path/to/deovr/root -S "https://example.com" -P foo -V video_file.mp4 --stereoMode='sbs' --screenType='dome' 

#  scan all playlist, clean deleted file from json
python generate_json.py -T /path/to/deovr/root -C

# update metadata

# overwrite all metadata. bit mask mean: 1: thumbnail, 2: preview video, 4: seeklookup video, 8: timeline preview image
python generate_json.py -T /path/to/deovr/root -P foo -F 15 #(1111)
# regenerate thumbnail for specific video, snapshot at 3s
python generate_json.py -T /path/to/deovr/root -P foo -V video_file.mp4 -F 1 -s 3
# scan all missing metadata, don't overwrite
python generate_json.py -T /path/to/deovr/root -P foo -F 16
```

### helper utility

```shell
# list all playlist and videos number
python utils.py -T /path/to/deovr/root list

# rename playlist name
python utils.py -T /path/to/deovr/root rename --src playlist1 --dst playlist2
# move all videos from playlist to another
python utils.py -T /path/to/deovr/root move --src playlist1 --dst playlist2
# move one video from playlist to another
python utils.py -T /path/to/deovr/root move --src playlist1 -V "title" --dst playlist2

# delete duplicate video in playlist
python utils.py -T /path/to/deovr/root dupdel --src playlist1 --ref playlist2
```

## help options

```shell
usage: deovr-dl.py [-h] [-u URL] [-O OUTPUT_DIR] [-t TITLE] [-y] [-C COOKIE_FILE] [-F] [-A] [-c ENCODING [ENCODING ...]] [-f SELECT_FORMAT_IDX]
                   [-L SKIP_POLICY] [-n THREAD_NUMBER] [-K CHUNK_SIZE] [-R FAILED_REPEAT] [-H] [-P PLAYLIST] [-S SERVER] [-E]

Download url from deovr

options:
  -h, --help            show this help message and exit
  -u URL, --url URL     URL of video page
  -O OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Output file dir
  -t TITLE, --title TITLE
                        Used to construct filename. If not set, parse title from web
  -y, --overwrite       overwrite exist
  -C COOKIE_FILE, --cookie-file COOKIE_FILE
                        cookie file
  -F, --list-format     list all available format
  -A, --ask-for-download
                        ask for download before download video
  -c ENCODING [ENCODING ...], --encoding ENCODING [ENCODING ...]
                        filter selected encoding. e.g -c h264 h265, default only h265
  -f SELECT_FORMAT_IDX, --select-format-idx SELECT_FORMAT_IDX
                        select format by index. If not set, select the best quality with filted encoding
  -L SKIP_POLICY, --skip-policy SKIP_POLICY
                        0: same res and encoding, 1: same encoding, 2: same title (diff encoding & res)
  -n THREAD_NUMBER, --thread-number THREAD_NUMBER
                        parallel download threads, 0 for original downloader
  -K CHUNK_SIZE, --chunk-size CHUNK_SIZE
                        Download in chunks of n bytes, default 20 MiB
  -R FAILED_REPEAT, --failed-repeat FAILED_REPEAT
                        download failed repeat times
  -H, --hosting-mode    normal mode: download single video. Hosting mode: download and organize
  -P PLAYLIST, --playlist PLAYLIST
                        playlist name, default `Library`. If the url is a playlist, the parsed playlist name will be used
  -S SERVER, --server SERVER
                        HTTP server address hosting the video files
  -E, --force-metadata  force download missed metadata, don't download video

```
