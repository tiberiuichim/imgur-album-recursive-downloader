import logging
import os
import re
import sys
from collections import UserDict
from datetime import datetime

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

STYLE = """
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
	<xsl:output method="html" indent="yes"/>
	<xsl:template name="UnixTime-to-dateTime">
		<!-- https://stackoverflow.com/a/58145572/401059 -->
		<xsl:param name="unixTime"/>

		<xsl:variable name="JDN" select="floor($unixTime div 86400) + 2440588" />
		<xsl:variable name="secs" select="$unixTime mod 86400" />

		<xsl:variable name="f" select="$JDN + 1401 + floor((floor((4 * $JDN + 274277) div 146097) * 3) div 4) - 38"/>
		<xsl:variable name="e" select="4*$f + 3"/>
		<xsl:variable name="g" select="floor(($e mod 1461) div 4)"/>
		<xsl:variable name="h" select="5*$g + 2"/>

		<xsl:variable name="d" select="floor(($h mod 153) div 5 ) + 1"/>
		<xsl:variable name="m" select="(floor($h div 153) + 2) mod 12 + 1"/>
		<xsl:variable name="y" select="floor($e div 1461) - 4716 + floor((14 - $m) div 12)"/>

		<xsl:variable name="H" select="floor($secs div 3600)"/>
		<xsl:variable name="M" select="floor($secs mod 3600 div 60)"/>
		<xsl:variable name="S" select="$secs mod 60"/>

		<xsl:value-of select="$y"/>
		<xsl:text>-</xsl:text>
		<xsl:value-of select="format-number($m, '00')"/>
		<xsl:text>-</xsl:text>
		<xsl:value-of select="format-number($d, '00')"/>
		<xsl:text> </xsl:text>
		<xsl:value-of select="format-number($H, '00')"/>
		<xsl:text>:</xsl:text>
		<xsl:value-of select="format-number($M, '00')"/>
		<xsl:text>:</xsl:text>
		<xsl:value-of select="format-number($S, '00')"/>
	</xsl:template>
	<xsl:template match="album">
		<html>
			<body style="background-color: #141518; color: #d9d9da; font-family: &quot;Open Sans&quot;, sans-serif">
				<!-- selection background color is #1bb76e; really just a gimmick -->
				<div style="max-width: 180mm; margin: 0px auto; background-color: #2c2f34;">
					<div style="padding: 20px 20px 25px;">
						<h1 style="font-size: 18px;">
							<xsl:value-of select="meta/title" />
						</h1>
						<small style="color: #bbb;">
							<xsl:choose>
								<xsl:when test="meta/account/url">
									by <b><xsl:value-of select="meta/account/url" /></b>
								</xsl:when>
								<xsl:otherwise>
									Uploaded
								</xsl:otherwise>
							</xsl:choose>
							&#8195;
							<xsl:call-template name="UnixTime-to-dateTime">
								<xsl:with-param name="unixTime" select="meta/datetime" />
							</xsl:call-template>
							&#8195;
							(archived: <xsl:call-template name="UnixTime-to-dateTime">
									<xsl:with-param name="unixTime" select="meta/archived" />
							</xsl:call-template>)
						</small>
					</div>
					<xsl:for-each select="content/entry">
						<div style="padding: 10px 0px;">
							<xsl:if test="id"><a id="{id}" /></xsl:if>
							<a id="{position()}" />
							<div style="background-color: black; width: 100%;">
								<xsl:choose>
									<xsl:when test="img">
										<a href="{img}">
											<img src="{img}" style="max-width:100%; margin: 0px auto; display: block;" />
										</a>
									</xsl:when>
									<xsl:when test="vid">
										<video loop="" autoplay="" muted="" controls="" style="max-width: 100%;">
											<source src="{vid}" />
											[Videos not supported by browser.]
										</video>
									</xsl:when>
									<xsl:otherwise>
										[ERROR: Data missing!]
									</xsl:otherwise>
								</xsl:choose>
							</div>
							<xsl:if test="desc"><div style="padding: 20px 20px 15px;">
								<xsl:copy-of select="desc/node()"/>
							</div></xsl:if>
						</div>
					</xsl:for-each>
				</div>
			</body>
		</html>
	</xsl:template>
</xsl:stylesheet>
"""

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


def save_image(info, destination, idx):
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
    filename = "%04d-%s.%s" % (idx, slug, suffix)
    filepath = os.path.join(destination, filename)

    download(info['link'], filepath)

    description = info['description']

    if description:
        if not G['xml']:
            txtpath = os.path.join(destination, '%04d-%s.txt' % (idx, slug))
            with open(txtpath, 'w') as f:
                f.write("Title: %s\r" % title)
                f.write("Description: %s\r" % description)

        if G['find-albums']:
            for album in find_albums(description):
                logger.info("Queuing download of album: %s", album)
                processor.put(lambda: download_album(album=album))

    typ = "img"
    if suffix in ["mp4", "webm", "ogv", "ogg"]:
        typ = "vid"
    if suffix in ["gifv"]:
        typ = "gifv" # doesn't actually exist?

    return {
        typ: filename,
        "title": info['title'],
        "id": info['id'],
        "desc": info['description']
    }


def get_album_id(url):
    """ Returns the album id for an url
    """

    if 'imgur.com' not in url:
        return

    if '/gallery/' in url:      # url such as https://imgur.com/gallery/Z0lda

        return url.split('/gallery/')[1]

    if '/a/' in url:
        return url.split('/a/')[1]

    if '/r/' in url:            # url such as https://imgur.com/r/pics/AAAAA
        return url.split('/')[-1]


def get_album_metadata(album):
    """ Retrieves the album metadata
    """

    endpoint = "https://api.imgur.com/3/album/%s" % album
    response = request(endpoint)

    res = response.json()

    if res['status'] != 200 or not(res['success']):
        return False

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

    if not meta:
        logger.error("Error retrieving album metadata for %s", album)

        return

    logger.info("Got album titled %s", meta['title'])

    destination = destination or G.base

    sluger = UniqueSlugify()        # uids=os.listdir(destination)

    if not meta['title']:
        meta['title'] = 'Unknown Artists - Untitled Album'

    album_id = sluger(meta['title'])
    album_path = os.path.join(destination, album_id)

    logger.debug("Saving album to %s", album_path)

    os.makedirs(album_path, exist_ok=True)

    if G['find-albums']:
        for album in find_albums(meta['description'] or ''):
            logger.info("Queuing download of album: %s", album)
            processor.put(lambda: download_album(album=album))

    if not G['xml']:
        with open(os.path.join(album_path, 'album-metadata.txt'), 'w') as f:
            f.write('Title %s\r' % meta['title'] or meta['id'])
            f.write('Album ID: %s\r' % album)
            f.write('Description: %s\r' % meta['description'] or '')

    endpoint = "https://api.imgur.com/3/album/%s/images" % album
    try:
        response = request(endpoint)
        res = response.json()
    except Exception:
        return False

    if res['status'] != 200 or not(res['success']):
        return False

    if not G['xml']:
        for idx, info in enumerate(res['data']):
            entry = save_image(info, album_path, idx)
    else:
        with open(os.path.join(album_path, 'index.xml'), 'w') as xml:
            xml.write(
                '<?xml version="1.0"?>\n' +
                '<?xml-stylesheet type="text/xsl" href="archive.xsl"?>\n' +
                '<!DOCTYPE album>\n' +
                '<album>\n' +
                '\t<meta>\n'+
                '\t\t<id>%s</id>\n' % album +
                '\t\t<title>%s</title>\n' % meta['title'] +
                ('\t\t<desc>%s</desc>\n' % meta['description'] if meta['description'] is not None else '') +
                '\t\t<account>\n' +
                '\t\t\t<url>%s</url>\n' % meta['account_url'] +
                '\t\t\t<id>%s</id>\n' % meta['account_id'] +
                '\t\t</account>\n' +
                '\t\t<datetime>%d</datetime>\n' % meta['datetime'] +
                '\t\t<archived>%d</archived>\n' % datetime.now(tz=None).timestamp() +
                '\t\t<views>%d</views>\n' % meta['views'] +
                '\t\t<nsfw>%s</nsfw>\n' % meta['nsfw'] +
                '\t</meta>\n' +
                '\t<content>\n'
            )
            xml.flush()

            for idx, info in enumerate(res['data']):
                entry = save_image(info, album_path, idx)
                xml.write('\t\t<entry>\n%s\t\t</entry>\n' % ''.join(
                    '\t\t\t<%s>%s</%s>\n' % (k, '<br />'.join(v.splitlines()), k) for k, v in entry.items() if v is not None
                ))

            xml.write('\t</content>\n</album>\n')

            with open(os.path.join(album_path, 'archive.xsl'), 'w') as style:
                style.write(STYLE)


def request(url):
    # authorization: Client-ID XXX
    headers = {'authorization': 'CLIENT-ID %s' % G.clientid}

    return requests.get(url, headers=headers)


@click.command()
@click.option('--recursive/--no-recursive',
              default=False,
              help="Discover other albums in image descriptions")
@click.option('--xml/--no-xml',
              default=False,
              help="Write an XML document containing titles and descriptions")
@click.option('-v', '--verbose', count=True, help="Verbose mode")
@click.argument("url")
@click.argument("destination")
def downloader(url, destination, recursive, verbose, xml):
    settings = get_settings()
    clientid = settings['clientid']

    destination = os.path.normpath(destination)

    if verbose:
        logger.setLevel(logging.DEBUG)

    G['clientid'] = clientid
    G['base'] = destination
    G['find-albums'] = recursive
    G['xml'] = xml

    processor.put(lambda: download_album(url=url))
    processor.start()
