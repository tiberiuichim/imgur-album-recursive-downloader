# imgur-album-recursive-downloader

Download imgur albums, optionally discovering more albums in image descriptions


### How to use

1. Use pip to install ImgurDownloader (``pip install ImgurDownloader``)
2. Run ``imgur http://imgur.com/a/Something path/to/some/folder``
3. If you want to recursively download albums (it discovers new albums in the description of images), run: ``imgur --recursive http://imgur.com/a/Something path/to/some/folder``

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

### Note

This app uses the Imgur.com developers API, so you'll need an imgur.com account to create a new application and generate a new clientid for your app. After that, you'll have to write the clientid in the configuration file, which is automatically generated for you when you first run the app, at ``~/.config/imgurdownloader/settings.conf``
