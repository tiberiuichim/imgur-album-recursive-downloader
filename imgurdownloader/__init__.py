import logging
import os
import re
import sys
from collections import UserDict

import click
import configparser
import requests
from queue import Queue

from slugify import UniqueSlugify
from xdg import XDG_CONFIG_HOME

NAME = "imgurdownloader"

CONF_TEMPLATE = """
[downloader]
# Use https://api.imgur.com/oauth2/addclient to generate a new clientid

clientid =
""".strip()

URLS_REGEX = 'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|' \
    '(?:%[0-9a-fA-F][0-9a-fA-F]))+'

logger = logging.getLogger(NAME)
logger.setLevel(logging.INFO)

logger.addHandler(logging.StreamHandler())


class GlobalSettings(UserDict):

    def __getattr__(self, k):
        return self[k]

G = GlobalSettings()        # singleton to store global configuration

seen = []                   # avoid re-downloading if albums link to each other


class Processor(Queue):
    """ A single-threaded processor for tasks
    """

    def start(self):
        while not self.empty():
            task = self.get()
            task()
            self.task_done()


processor = Processor()


def find_albums(text):
    logger.debug("Finding links in: %s", text)
    urls = set(re.findall(URLS_REGEX, text))

    return filter(None, [get_album_id(l) for l in urls])


def get_settings():
    """ Returns a dictionary of settings
    """
    base = os.path.join(XDG_CONFIG_HOME, NAME)
    conf = os.path.join(base, "settings.conf")

    settings = {}

    if os.path.exists(conf):
        parser = configparser.SafeConfigParser()
        parser.read(conf)

        if 'downloader' not in parser.sections():
            print('Please add downloader section in conf file')
            sys.exit(1)

        options = parser.options('downloader')

        for opt in options:
            settings[opt] = parser.get('downloader', opt)
    else:
        os.makedirs(base, exist_ok=True)
        with open(conf, 'w') as f:
            f.write(CONF_TEMPLATE)

    if 'clientid' not in settings:
        print("Please set clientid value in '%s'" % conf)
        print("Use https://api.imgur.com/oauth2/addclient to generate one")
        sys.exit(1)

    return settings


def download(link, destination):
    resp = requests.get(link, stream=True)
    with open(destination, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=1024):
            f.write(chunk)


def save_image(info, destination):
    """ Downloads the image to the URL

    @param info: dict with metadata about image
    @param destination: directory where to download
    """

    url = info['link']
    logger.info("Downloading %s", url)

    suffix = url.split('/')[-1].split('.')[-1]

    if not suffix or '.' not in suffix:
        suffix = info['type'].split('/')[-1]

    if suffix == 'jpeg':
        suffix = 'jpg'

    title = info['title'] or info['id']

    sluger = UniqueSlugify(uids=os.listdir(destination))
    slug = sluger(title)
    filename = "%s.%s" % (slug, suffix)
    filepath = os.path.join(destination, filename)

    download(info['link'], filepath)

    description = info['description']

    if description:
        txtpath = os.path.join(destination, '%s.txt' % slug)
        with open(txtpath, 'w') as f:
            f.write("Title: %s\r" % title)
            f.write("Description: %s\r" % description)

        if G['find-albums']:
            for album in find_albums(description):
                logger.info("Queuing download of album: %s", album)
                processor.put(lambda: download_album(album=album))


def get_album_id(url):
    """ Returns the album id for an url
    """

    if 'imgur.com' not in url:
        return

    if '/gallery/' in url:
        # https://imgur.com/gallery/Z0lda

        return url.split('/gallery/')[1]

    if '/a/' in url:
        return url.split('/a/')[1]


def get_album_metadata(album):
    """ Retrieves the album metadata
    """

    endpoint = "https://api.imgur.com/3/album/%s" % album
    response = request(endpoint)

    res = response.json()

    return res['data']


def download_album(url=None, album=None, destination=None):
    """ Downloads the album to the destination.

    Returns success status
    """

    if not (url or album):
        raise ValueError

    logger.debug("Retrieving info on album %s", url or album)

    if url:
        album = get_album_id(url)

    if album in seen:
        return
    else:
        seen.append(album)

    meta = get_album_metadata(album)

    logger.info("Got album titled %s", meta['title'])

    destination = destination or G.base

    sluger = UniqueSlugify()        # uids=os.listdir(destination)
    album_id = sluger(meta['title'])
    album_path = os.path.join(destination, album_id)

    logger.debug("Saving album to %s", album_path)

    os.makedirs(album_path, exist_ok=True)

    with open(os.path.join(album_path, 'album-metadata.txt'), 'w') as f:
        f.write('Title %s\r' % meta['title'] or meta['id'])
        f.write('Album ID: %s\r' % album)

    endpoint = "https://api.imgur.com/3/album/%s/images" % album
    try:
        response = request(endpoint)
        res = response.json()
    except Exception:
        return False

    if res['status'] != 200 or not(res['success']):
        return False

    for info in res['data']:
        save_image(info, album_path)


def request(url):
    # authorization: Client-ID XXX
    headers = {'authorization': 'CLIENT-ID %s' % G.clientid}

    return requests.get(url, headers=headers)


@click.command()
@click.option('--recursive/--no-recursive',
              default=False,
              help="Discover other albums in image descriptions")
@click.option('-v', '--verbose', count=True, help="Verbose mode")
@click.argument("url")
@click.argument("destination")
def downloader(url, destination, recursive, verbose):
    settings = get_settings()
    clientid = settings['clientid']

    destination = os.path.normpath(destination)

    if verbose:
        logger.setLevel(logging.DEBUG)

    G['clientid'] = clientid
    G['base'] = destination
    G['find-albums'] = recursive

    processor.put(lambda: download_album(url=url))
    processor.start()
