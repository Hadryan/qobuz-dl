import os

import requests
from pathvalidate import sanitize_filename
from tqdm import tqdm

import qobuz_dl.metadata as metadata


def tqdm_download(url, fname, track_name):
    r = requests.get(url, allow_redirects=True, stream=True)
    total = int(r.headers.get("content-length", 0))
    with open(fname, "wb") as file, tqdm(
        total=total,
        unit="iB",
        unit_scale=True,
        unit_divisor=1024,
        desc=track_name,
        bar_format="{n_fmt}/{total_fmt} /// {desc}",
    ) as bar:
        for data in r.iter_content(chunk_size=1024):
            size = file.write(data)
            bar.update(size)


def mkDir(dirn):
    try:
        os.makedirs(dirn, exist_ok=True)
    except FileExistsError:
        pass


def getDesc(u, mt, multiple=None):
    return "{} [{}/{}]".format(
        ("[Disc {}] {}".format(multiple, mt["title"])) if multiple else mt["title"],
        u["bit_depth"],
        u["sampling_rate"],
    )


def get_format(album_dict, quality):
    try:
        if int(quality) == 5:
            return "MP3"
        if album_dict["maximum_bit_depth"] == 16 and int(quality) < 7:
            return "FLAC"
    except KeyError:
        return "Unknown"
    return "Hi-Res"


def get_extra(i, dirn, extra="cover.jpg"):
    tqdm_download(i, os.path.join(dirn, extra), "Downloading " + extra.split(".")[0])


# Download and tag a file
def download_and_tag(
    root_dir,
    tmp_count,
    track_url_dict,
    track_metadata,
    album_or_track_metadata,
    is_track,
    is_mp3,
    embed_art=False,
    multiple=None,
):
    """
    Download and tag a file

    :param str root_dir: Root directory where the track will be stored
    :param int tmp_count: Temporal download file number
    :param dict track_url_dict: get_track_url dictionary from Qobuz client
    :param dict track_metadata: Track item dictionary from Qobuz client
    :param dict album_or_track_metadata: Album/track dictionary from Qobuz client
    :param bool is_track
    :param bool is_mp3
    :param bool embed_art: Embed cover art into file (FLAC-only)
    :param multiple: Multiple disc integer
    :type multiple: integer or None
    """
    extension = ".mp3" if is_mp3 else ".flac"

    try:
        url = track_url_dict["url"]
    except KeyError:
        print("Track not available for download")
        return

    if multiple:
        root_dir = os.path.join(root_dir, "Disc " + str(multiple))
        mkDir(root_dir)

    filename = os.path.join(root_dir, ".{:02}".format(tmp_count) + extension)

    new_track_title = sanitize_filename(track_metadata["title"])
    track_file = "{:02}. {}{}".format(
        track_metadata["track_number"], new_track_title, extension
    )
    final_file = os.path.join(root_dir, track_file)
    if os.path.isfile(final_file):
        print(track_metadata["title"] + " was already downloaded. Skipping...")
        return

    desc = getDesc(track_url_dict, track_metadata, multiple)
    tqdm_download(url, filename, desc)
    tag_function = metadata.tag_mp3 if is_mp3 else metadata.tag_flac
    try:
        tag_function(
            filename,
            root_dir,
            final_file,
            track_metadata,
            album_or_track_metadata,
            is_track,
            embed_art,
        )
    except Exception as e:
        print("Error tagging the file: " + str(e))
        os.remove(filename)


def download_id_by_type(client, item_id, path, quality, album=False, embed_art=False):
    """
    Download and get metadata by ID and type (album or track)

    :param Qopy client: qopy Client
    :param int item_id: Qobuz item id
    :param str path: The root directory where the item will be downloaded
    :param int quality: Audio quality (5, 6, 7, 27)
    :param bool album
    """
    count = 0

    if album:
        meta = client.get_album_meta(item_id)
        album_title = (
            "{} ({})".format(meta["title"], meta["version"])
            if meta["version"]
            else meta["title"]
        )
        print("\nDownloading: {}\n".format(album_title))
        dirT = (
            meta["artist"]["name"],
            album_title,
            meta["release_date_original"].split("-")[0],
            get_format(meta, quality),
        )
        sanitized_title = sanitize_filename("{} - {} [{}] [{}]".format(*dirT))
        dirn = os.path.join(path, sanitized_title)
        mkDir(dirn)
        get_extra(meta["image"]["large"], dirn)
        if "goodies" in meta:
            try:
                get_extra(meta["goodies"][0]["url"], dirn, "booklet.pdf")
            except Exception as e:
                print("Error: " + e)
        media_numbers = [track["media_number"] for track in meta["tracks"]["items"]]
        is_multiple = True if len([*{*media_numbers}]) > 1 else False
        for i in meta["tracks"]["items"]:
            parse = client.get_track_url(i["id"], quality)
            if "sample" not in parse and parse["sampling_rate"]:
                is_mp3 = True if int(quality) == 5 else False
                download_and_tag(
                    dirn,
                    count,
                    parse,
                    i,
                    meta,
                    False,
                    is_mp3,
                    embed_art,
                    i["media_number"] if is_multiple else None,
                )
            else:
                print("Demo. Skipping")
            count = count + 1
    else:
        parse = client.get_track_url(item_id, quality)

        if "sample" not in parse and parse["sampling_rate"]:
            meta = client.get_track_meta(item_id)
            track_title = (
                "{} ({})".format(meta["title"], meta["version"])
                if meta["version"]
                else meta["title"]
            )
            print("\nDownloading: {}\n".format(track_title))
            dirT = (
                meta["album"]["artist"]["name"],
                track_title,
                meta["album"]["release_date_original"].split("-")[0],
                get_format(meta, quality),
            )
            sanitized_title = sanitize_filename("{} - {} [{}] [{}]".format(*dirT))
            dirn = os.path.join(path, sanitized_title)
            mkDir(dirn)
            get_extra(meta["album"]["image"]["large"], dirn)
            is_mp3 = True if int(quality) == 5 else False
            download_and_tag(dirn, count, parse, meta, meta, True, is_mp3, embed_art)
        else:
            print("Demo. Skipping")
    print("\nCompleted\n")
