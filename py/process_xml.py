#
# Copyright (c) 2016 the authors of the https://github.com/publicdocs project.
# Use of this file is subject to the NOTICE file in the root of the repository.
#

# OVERVIEW:
# We want to take the XML version of the US Code, as published by the Office of the
# Law Revision Counsel, convert it into a format that can be easily viewed in a
# Git repository, and view how it changes over time as Git revision history.
# Due to the limitations of most Git visualization software, this requires breaking up
# the Code into multiple text-like files.
#
# For the original downloads see, see: http://uscode.house.gov/download/download.shtml
#
# As of 2016-Aug-29, http://uscode.house.gov/robots.txt doesn't disallow all bots,
# but, regardless, we want to be courteous and be sure not to overload their servers.
#
# Store the hash of the ZIP file. This is especially important since we couldn't
# find an HTTPS download for these files =(
#

import urllib2
import hashlib
import os
import zlib
import argparse
import shutil
import StringIO
import zipfile


from xml.etree import ElementTree
from string import Template
from collections import namedtuple

## CONSTANTS

_out_header_markdown = Template(u"""# US Code, Title $title, $filepart

**Important notes:**

* Use of this file is subject to the NOTICE at [https://github.com/publicdocs/uscode/blob/master/NOTICE](https://github.com/publicdocs/uscode/blob/master/NOTICE)
* This file is generated from historical data.
* See the [Document Metadata](${docmd}) for more information.
* Furthermore, the system is a work in progress, and it is likely a lot of content and formatting is incorrect.

----------
----------

$links

$innercontent

""")


_out_readme_markdown = Template(u"""# US Code, Title $title, Release Point ${rp1}-${rp2}

**Important notes:**

* Use of this file is subject to the NOTICE at [https://github.com/publicdocs/uscode/blob/master/NOTICE](https://github.com/publicdocs/uscode/blob/master/NOTICE)
* This file is generated from historical data and may not be current.
* Furthermore, the system is a work in progress, and it is likely a lot of content and formatting is incorrect.

----------

## Document Metadata

This is a modified and processed version of the US Code,
generated by the https://github.com/publicdocs project.

* Original provenance
    * URL: $url
    * SHA 512 digest = $sha512zip
    * Release Point: ${rp1}-${rp2}
* Title $title
    * XML File: $titlefile
    * SHA 512 digest = $sha512xml

For more information on the original source, see:
http://uscode.house.gov/download/download.shtml

XML file metadata:

```
$origmd
```

## Important Notice

```
$notice
```


----------

## Contents

$index

""")

_download_url_template = Template('http://uscode.house.gov/download/releasepoints/us/pl/$rp1/$rp2/xml_uscAll@$rp1-$rp2.zip')

NBSP = u"\u00A0"

_sp = "{http://xml.house.gov/schemas/uslm/1.0}"
TAG_META = _sp + "meta"

TAG_TITLE = _sp + "title"
TAG_SUBTITLE = _sp + "subtitle"
TAG_CHAPTER = _sp + "chapter"
TAG_SUBCHAPTER = _sp + "subchapter"
TAG_PART = _sp + "part"
TAG_SUBPART = _sp + "subpart"
TAG_DIVISION = _sp + "division"
TAG_SUBDIVISION = _sp + "subdivision"
TAG_ARTICLE = _sp + "article"
TAG_SUBARTICLE = _sp + "subarticle"
TAG_SECTION = _sp + "section"

TAGS_LARGE = [TAG_TITLE, TAG_SUBTITLE, TAG_CHAPTER, TAG_SUBCHAPTER, TAG_PART, TAG_SUBPART, TAG_DIVISION, TAG_SUBDIVISION, TAG_ARTICLE, TAG_SUBARTICLE]
TAGS_HEADINGS = []
TAGS_HEADINGS.extend(TAGS_LARGE)
TAGS_HEADINGS.append(TAG_SECTION)

TAG_SUBSECTION = _sp + "subsection"
TAG_PARAGRAPH = _sp + "paragraph"
TAG_SUBPARAGRAPH = _sp + "subparagraph"
TAG_CLAUSE = _sp + "clause"
TAG_SUBCLAUSE = _sp + "subclause"
TAG_ITEM = _sp + "item"
TAG_SUBITEM = _sp + "subitem"
TAG_SUBSUBITEM = _sp + "subsubitem"

TAGS_SMALL = [TAG_SUBSECTION, TAG_PARAGRAPH, TAG_SUBPARAGRAPH, TAG_CLAUSE, TAG_SUBCLAUSE, TAG_ITEM, TAG_SUBITEM, TAG_SUBSUBITEM]

TAG_HEADING = _sp + "heading"
TAGS_BOLDEN = [TAG_HEADING]

TAG_CHAPEAU = _sp + "chapeau"
TAG_CONTENT = _sp + "content"
TAG_CONTINUATION = _sp + "continuation"
TAG_P = _sp + "p"

TAG_QUOTEDCONTENT = _sp + "quotedContent"
TAGS_QUOTED = [TAG_QUOTEDCONTENT]

TAGS_BREAK = [TAG_CHAPEAU, TAG_CONTENT, TAG_CONTINUATION, TAG_P]
TAGS_BREAK.extend(TAGS_HEADINGS)
TAGS_BREAK.extend(TAGS_SMALL)

## STRUCTURES
ZipContents = namedtuple("ZipContents", "sha512 titledir")
ProcessedElement = namedtuple("ProcessedElement", "inputmeta outputmd tail")
FileDelimiter = namedtuple("FileDelimiter", "identifier dir titleroot reporoot prev next filename")
FileDelimiter.__new__.__defaults__ = (None, ) * len(FileDelimiter._fields)

## FUNCTIONS

# A release point is labeled like Public Law 114-195, i.e. Public Law rp1-rp2
def download(rp1, rp2):
    # TODO, for now just manually download the file
    return 0


def md_header_prefix(identifier):
    # An identifier of /us/usc/t1/s1 gets two chars: ==
    # and we never have more than 6 chars
    c = unicode(identifier).count(u'/') - 2
    if c > 6:
        c = 6
    return (u"#" * c) + u" "


def md_indent(clazz):
    ind = 0
    if u"indent10" in clazz:
        ind = 11
    elif u"indent9" in clazz:
        ind = 10
    elif u"indent8" in clazz:
        ind = 9
    elif u"indent7" in clazz:
        ind = 8
    elif u"indent6" in clazz:
        ind = 7
    elif u"indent5" in clazz:
        ind = 6
    elif u"indent4" in clazz:
        ind = 5
    elif u"indent3" in clazz:
        ind = 4
    elif u"indent2" in clazz:
        ind = 3
    elif u"indent1" in clazz:
        ind = 2
    elif u"indent0" in clazz:
        ind = 1
    return NBSP * (ind * 2)


def process_zip(input_zip, wd):
    wdir = wd + '/unzipped'
    if os.path.exists(wdir):
        shutil.rmtree(wdir)
    os.makedirs(wdir)
    hasher = hashlib.sha512()
    try:
        hasher.update(input_zip.read())
        input_zip.seek(0)
        zip = zipfile.ZipFile(input_zip, 'r')
        zip.extractall(wdir)
    finally:
        input_zip.close()
    sha = hasher.hexdigest()
    return ZipContents(sha512 = sha, titledir = wdir)

def prep_output(wd):
    wdir = wd + '/gen'
    if os.path.exists(wdir):
        shutil.rmtree(wdir)
    os.makedirs(wdir)

def process_element(elem, nofmt = False):
    meta = u''
    tag = elem.tag
    text = elem.text
    attrib = elem.attrib
    tail = elem.tail
    outputs = []
    filesep = None
    cid = None
    content_pre = u''
    content_post = u''
    chnofmt = False
    if tag == TAG_META:
        meta = ElementTree.tostring(elem, "UTF-8", "html")
    else:
        if elem.get('identifier') and (tag in TAGS_HEADINGS):
            cid = elem.get('identifier')
            filesep = unicode(cid)
            chnofmt = True
            outputs.append(u'\n\n' + md_header_prefix(cid))
        elif tag in TAGS_BREAK:
            outputs.append(u'\n\n')
        elif tag in TAGS_BOLDEN:
            if not nofmt:
                content_pre = u' __'
                content_post = u'__ '
        elif tag in TAGS_QUOTED:
            if not nofmt:
                content_pre = u'\n> '
                content_post = u' '

        if text:
            if text.strip() and (content_pre or content_post):
                outputs.append(content_pre + unicode(text).strip() + content_post)
            else:
                outputs.append(unicode(text))

        for child in elem:
            p = process_element(child, chnofmt)
            if p.outputmd:
                outputs.extend(p.outputmd)
            if p.inputmeta:
                meta = meta + p.inputmeta
            if p.tail:
                if p.tail.strip() and (content_pre or content_post):
                    outputs.append(content_pre + unicode(p.tail).strip() + content_post)
                else:
                    outputs.append(unicode(p.tail))

    ind = u""
    if elem.get('class'):
        ind = md_indent(elem.get('class'))

    outputs2 = []
    lastnl = True
    for o in outputs:
        if isinstance(o, FileDelimiter):
            lastnl = True
            outputs2.append(o)
        else:
            if o.strip() and lastnl:
                outputs2.append(ind + o)
            else:
                outputs2.append(o)
            lastnl = o.endswith(u'\n')

    if filesep:
        if tag == TAG_SECTION:
            outputs2.insert(0, FileDelimiter(identifier=filesep, dir=None))
        else:
            outputs2.insert(0, FileDelimiter(identifier=filesep, dir=filesep))

    return ProcessedElement(inputmeta = meta, outputmd = outputs2, tail = elem.tail)

def process_title(zip_contents, title, rp1, rp2, notice, wd):
    wdir = wd + '/gen/titles/usc' + title
    if os.path.exists(wdir):
        shutil.rmtree(wdir)
    os.makedirs(wdir)
    of = wdir + '/title.md'
    zipurl = _download_url_template.substitute(rp1 = rp1, rp2 = rp2)
    titlefilename = "usc" + title + ".xml"
    moredir = "xml/"
    if rp1 == "113" and rp2 == "21":
        moredir = ""
    titlepath = zip_contents.titledir + "/" + moredir + titlefilename


    hasher = hashlib.sha512()
    try:
        hasher.update(open(titlepath, 'r').read())
    except:
        print "Could not read title " + str(title)
        return -1
    xmlsha = hasher.hexdigest()

    origxml = ElementTree.parse(titlepath).getroot()



    p = process_element(origxml)
    outsets = []
    fd = None
    lastdir = None
    lastoutset = []


    inc = 0
    osss = p.outputmd
    # dummy terminator
    osss.append(FileDelimiter())
    for o in osss:
        if isinstance(o, FileDelimiter):
            #print 'Found fd', o
            if fd:
                cid = fd.identifier
                # titleroot reporoot prev next filename
                fn = (u'/m_') + cid.replace(u'/', u'_') + u'.md'
                tr = u'./' + (u'../' * lastdir.count(u'/'))
                outsets.append([fd._replace(titleroot = tr, dir=lastdir, filename = fn), lastoutset])
                lastoutset = []
                inc = inc + 1
            fd = o
            if o.dir:
                lastdir = o.dir
        else:
            lastoutset.append(o)

    outsets2 = []
    ll = len(outsets)
    for idx, o in enumerate(outsets):
        fd = o[0]
        lo = o[1]
        lprev = None
        lnext = None
        if idx > 0:
            lp = outsets[idx - 1][0]
            lprev = fd.titleroot + lp.dir + lp.filename
        if idx < ll - 1:
            ln = outsets[idx + 1][0]
            lnext = fd.titleroot + ln.dir + ln.filename
        outsets2.append([fd._replace(prev = lprev, next = lnext), lo])

    finaloutsets = outsets2

    print "Generating " + str(inc) + " entries for title " + str(title)

    index = u'\n\n'

    for outs in finaloutsets:
        fd = outs[0]
        cid = outs[0].identifier
        cdir = wdir + u'/' + outs[0].dir
        if not os.path.exists(cdir):
            os.makedirs(cdir)
        of = cdir + '/' + outs[0].filename
        ofl = u'./' + outs[0].dir + u'/' + outs[0].filename

        innercontent = StringIO.StringIO()
        innercontent.write(u''.join(outs[1]))
        cont = innercontent.getvalue()
        cont = u'\n\n'.join([line for line in cont.splitlines() if line.strip()])
        idn = fd.dir.count(u'/') - 3
        if not (fd.dir == cid):
            idn = idn + 1
        index = index + (u'  ' * (idn)) +  u'* [' + cid+ u']('+ ofl  +u')\n'
        linkhtml = u''
        if fd.prev:
            linkhtml = linkhtml + u'[Previous](' + fd.prev + u') | '
        else:
            linkhtml = linkhtml + u'~~Previous~~ | '


        if fd.next:
            linkhtml = linkhtml + u'[Next](' + fd.next + u') | '
        else:
            linkhtml = linkhtml + u'~~Next~~ | '

        if fd.titleroot:
            linkhtml = linkhtml + u'[Root of Title](' + fd.titleroot + u')'
        else:
            linkhtml = linkhtml + u'~~Root of Title~~'

        fc = _out_header_markdown.substitute(
                rp1 = rp1,
                rp2 = rp2,
                url = zipurl,
                sha512zip = zip_contents.sha512,
                titlefile = titlefilename,
                docmd = u'./' + fd.titleroot + '/README.md',
                sha512xml = xmlsha,
                filepart = unicode(cid),
                notice = notice,
                origmd = p.inputmeta,
                title = title,
                links = linkhtml,
                innercontent = cont,
        )
        f = open(of, 'w')
        f.write(fc.encode('utf8'))
        f.close()
        inc = inc + 1

    of = wdir + '/README.md'
    fc = _out_readme_markdown.substitute(
            rp1 = rp1,
            rp2 = rp2,
            url = zipurl,
            sha512zip = zip_contents.sha512,
            titlefile = titlefilename,
            sha512xml = xmlsha,
            notice = notice,
            origmd = p.inputmeta,
            title = title,
            index = index,
    )
    f = open(of, 'w')
    f.write(fc.encode('utf8'))
    f.close()

def main():
    parser = argparse.ArgumentParser(description='Generates publicdocs project US Code files.')
    parser.add_argument('--ua', dest='useragent', action='store',
                        default='',
                        help='user agent for downloading files')
    parser.add_argument('--wd', '--working-dir', dest='working_directory', action='store',
                        default='working/',
                        help='working directory for temporary files generated by processing')
    parser.add_argument('--o', '--output-dir', dest='output_directory', action='store',
                        default='out/',
                        help='output directory for final files generated by processing')
    parser.add_argument('--clear-out', dest='clear_out', action='store_true',
                        help='clears the output directory first')
    parser.add_argument('--i', '--input-zip', dest='input_zip', action='store', type=file,
                        help='path to input zip file')
    parser.add_argument('--notice', dest='notice_file', action='store', type=file,
                        help='path to input NOTICE file')
    parser.add_argument('--rp1', dest='rp1', action='store',
                        help='First part of the release point id, ex. 114 in Public Law 114-195')
    parser.add_argument('--rp2', dest='rp2', action='store',
                        help='Second part of the release point id, ex. 195 in Public Law 114-195')
    parser.add_argument('--titles', dest='titles', nargs='*',
                        help='List of title numbers to process, or none to process all')

    args = parser.parse_args()
    #print args
    if args.input_zip:
        z = process_zip(args.input_zip, args.working_directory)
        notice = args.notice_file.read()
        prep_output(args.working_directory)
        for title in args.titles:
            process_title(z, title, args.rp1, args.rp2, notice, args.working_directory)
    else:
        print "Could not determine operating mode"
        assert(False)

if __name__ == "__main__":
    main()
