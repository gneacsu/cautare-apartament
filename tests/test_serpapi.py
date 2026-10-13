from dataclasses import replace
from unittest.mock import Mock

import pytest
import requests

from src.config import Settings, ConfigurationError
from src.search.serpapi import SerpApiSearch
from src.analyzers.provider import ProviderError


def client(data,status=200):
    session=Mock()
    session.get.return_value.status_code=status
    session.get.return_value.json.return_value=data
    return SerpApiSearch(replace(Settings(),serpapi_key='secret-test'),session),session


def test_search_contract_localized_and_safe_pagination():
    api,session=client({'search_metadata':{'status':'Success'},'organic_results':[
        {'title':'Anunț','link':'https://example.com/a?utm_source=x','snippet':'Proprietar'},
        {'link':'https://example.com/a'}],
        'serpapi_pagination':{'next':'https://serpapi.com/search.json?api_key=secret-test&start=10'}})
    result=api.search('"fragment"',60)
    assert len(result.hits)==1 and result.next_start==10
    args=session.get.call_args
    assert args.args==('https://serpapi.com/search.json',)
    assert args.kwargs['params']['hl']=='ro' and args.kwargs['params']['gl']=='ro'
    assert args.kwargs['allow_redirects'] is False
    assert 'secret-test' not in str(api.calls)


@pytest.mark.parametrize('status',[401,403,429,500,302])
def test_http_errors_sanitized(status):
    api,session=client({},status)
    with pytest.raises(ProviderError) as exc:api.search('query',30)
    assert 'secret-test' not in str(exc.value)
    assert api.calls[0].outcome=='error'


@pytest.mark.parametrize('data',[
    {},{'error':'Invalid key secret-test'},{'search_metadata':{'status':'Processing'}},
    {'search_metadata':{'status':'Success'},'organic_results':[{'invalid':1}]},
    {'search_metadata':{'status':'Success'},'organic_results':'bad'},
])
def test_malformed_or_partial_is_not_negative(data):
    api,_=client(data)
    with pytest.raises(ProviderError) as exc:api.search('query',30)
    assert 'secret-test' not in str(exc.value)


def test_empty_success_is_valid():
    api,_=client({'search_metadata':{'status':'Success'},'error':"Google hasn't returned any results for this query."})
    assert api.search('query',30).hits==[]


def test_network_error_does_not_leak_request_url():
    api,session=client({})
    session.get.side_effect=requests.ConnectionError('https://serpapi.com/search?api_key=secret-test')
    with pytest.raises(ProviderError) as exc:api.search('query',30)
    assert 'secret-test' not in str(exc.value)


def test_missing_key_requires_no_request():
    api=SerpApiSearch(Settings(),Mock())
    with pytest.raises(ConfigurationError):api.search('query',30)
    api.session.get.assert_not_called()
