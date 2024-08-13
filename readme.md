## Intro

[DeoVR](https://deovr.com/) is a great VR video streaming platform. It features a large amount of user-uploaded content, including many high-quality videos such as cosplay convention, various tech expos, travel vlogs, and more. The video resolution is also very high, with regular users able to watch single-eye 4160p videos for free. However, DeoVR does have a downside: videos that were previously available for free may become exclusive to members after some time. Therefore, for videos you really like, it's crucial to download them.

Currently, only members of DeoVR can download 3 videos per month. And the yt-dlp project does not yet support the DeoVR website.

To address the above issues, this script is used to download videos from DeoVR offline.

## Usage

### Install

```shell
pip install -r requirements.txt
```

### Download single video

```shell
python deovr-dl.py -u https://deovr.com/oraehm          # download h264 best quality video
python deovr-dl.py -O ./output -u https://deovr.com/oraehm       # specify output dir
python deovr-dl.py -u https://deovr.com/oraehm -F       # list all available format
python deovr-dl.py -u https://deovr.com/oraehm -f 0     # select format by index
python deovr-dl.py -u https://deovr.com/oraehm -c h265     # download h265 best quality video
python deovr-dl.py -O ./output -u https://deovr.com/oraehm -n 6  # specify thread number
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
python deovr-dl.py -O /path/to/deovr_root/ -H -S "https://example.com" -u https://deovr.com/xxx  # -H mean hosting mode
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

## help options

```shell
usage: deovr-dl.py [-h] [-u URL] [-O OUTPUT_DIR] [-t TITLE] [-y] [-C COOKIE_FILE] [-F] [-c ENCODING [ENCODING ...]] [-f SELECT_FORMAT_IDX]
                   [-n THREAD_NUMBER] [-K CHUNK_SIZE] [-H] [-P PLAYLIST] [-S SERVER]

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
  -c ENCODING [ENCODING ...], --encoding ENCODING [ENCODING ...]
                        filter selected encoding. e.g -c h264 h265, default only h264
  -f SELECT_FORMAT_IDX, --select-format-idx SELECT_FORMAT_IDX
                        select format by index. If not set, select the best quality with filted encoding
  -n THREAD_NUMBER, --thread-number THREAD_NUMBER
                        parallel download threads, 0 for original downloader
  -K CHUNK_SIZE, --chunk-size CHUNK_SIZE
                        Download in chunks of n bytes, default 20 MiB
  -H, --hosting-mode    normal mode: download single video. Hosting mode: download and organize
  -P PLAYLIST, --playlist PLAYLIST
                        playlist name, default `Library`. If the url is a playlist, the parsed playlist name will be used
  -S SERVER, --server SERVER
                        HTTP server address hosting the video files

```
