# imgur-album-recursive-downloader

Download imgur albums, optionally discovering more albums in image descriptions

### How to use (in development mode)

1. Install virtualenv
2. Clone this repo
3. Activate in virtualenv (``pip install -e path/to/clone``)
4. ``<virtualenv>/bin/imgur --recursive -v http://imgur.com/a/Z0lda path/to/some/folder``

### Why another downloader?

The existing album downloader had a few problems:

- It didn't grab the highest resolution of images.
- It didn't save titles or descriptions of images
- It didn't try to find other albums in the description of images
