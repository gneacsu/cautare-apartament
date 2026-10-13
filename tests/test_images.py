import io
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest
from PIL import Image, ImageDraw

from src.extractors.images import image_urls, signature, match_images, decode_image, ImageError, fetch_image
from src.config import Settings
from src.models import Source, ImageMatch
from src.analyzers.verification import sufficiently_supported
from tests.test_core import listing,assessment


def picture(color='red',size=(400,300)):
    im=Image.new('RGB',size,'white'); d=ImageDraw.Draw(im)
    d.rectangle((size[0]//10,size[1]//10,size[0]//2,size[1]//2),fill=color)
    d.line((0,size[1],size[0],0),fill='black',width=10)
    buffer=io.BytesIO();im.save(buffer,'PNG');return buffer.getvalue()


def test_extract_images_and_exclude_logo():
    html='''<meta property="og:image" content="/a.jpg"><main><img src="/a.jpg"><img alt="logo" src="/logo.jpg"><img src="/b.jpg"></main>'''
    assert image_urls(html,'https://example.com/ad')==['https://example.com/a.jpg','https://example.com/b.jpg']


def test_image_identity_and_unrelated_images():
    a=signature(picture(),'reference')
    b=signature(picture(),'candidate')
    assert match_images([a],[b])[0].kind=='identical'
    im=Image.new('RGB',(400,300),'black');d=ImageDraw.Draw(im)
    for x in range(0,400,20):d.rectangle((x,0,x+10,300),fill='white')
    out=io.BytesIO();im.save(out,'PNG')
    assert not match_images([a],[signature(out.getvalue(),'other')])


def test_invalid_or_tiny_image_rejected():
    with pytest.raises(ImageError):decode_image(b'not image')
    with pytest.raises(ImageError):signature(picture(size=(40,30)),'small')


def test_image_similarity_alone_does_not_establish_property():
    source=Source(url='https://example.com/a',access='page',accessed_at='today',
                  image_matches=[ImageMatch(reference_url='a',candidate_url='b',kind='similar')])
    assert not sufficiently_supported(listing(),assessment(),source)


def test_image_fetch_checks_each_redirect():
    response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
    response.is_redirect=True;response.headers={'Location':'http://127.0.0.1/secret'}
    from src.utils.urls import InvalidURL
    with patch('src.extractors.images.public_url',side_effect=['https://example.com/a',InvalidURL('blocked')]) as validate,patch('src.extractors.images.requests.get',return_value=response):
        import time
        with pytest.raises(ImageError):fetch_image('https://example.com/a',Settings(),time.monotonic()+20)
        assert validate.call_count==2
