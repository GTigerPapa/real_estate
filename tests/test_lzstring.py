from urllib.parse import unquote

from realestate.lzstring import compress_uri, decompress_uri

# 사용자가 브라우저에서 복사한 네이버페이 부동산 지도 URL의 layer 값 (실제 값)
REAL = {
    121977: "NobwRAlgJmBcYGMD2BbADgGwKYA8D6UWALgIYQZgA0YaJATiSgM5zjLrY4CSMsAjACY%2BATgDsogL7UmWeggAWABXqMWscKQBGcMEQYA7JiQREISfWClg6xAK519JTdjh7bWCQF0gA",
    102283: "NobwRAlgJmBcYGMD2BbADgGwKYA8D6UWALgIYQZgA0YaJATiSgM5zjLrY4CSMsAjAAYATEIAcAZgC%2B1JlnoIAFgAV6jFrHCkARnDBEGAOyYkERCEgNUw9MwmwAVBoXsBPNFnVgAgnwC0AIT4rfRIjEzMLJRcsCwBzV3cAOQBXFC0sOl1RYMNjU3MDRxJnNyxdHzBpMDpiZLoDEi1sOH1krEkAXSA",
}


def test_decompress_real_urls():
    assert '"complexId":121977' in decompress_uri(unquote(REAL[121977]))
    assert '"complexId":102283' in decompress_uri(unquote(REAL[102283]))


def test_compress_matches_browser_output():
    # 우리 압축 결과가 브라우저가 만든 값과 글자 단위로 같아야 한다
    for v in REAL.values():
        s = unquote(v)
        assert compress_uri(decompress_uri(s)) == s


def test_roundtrip_unicode():
    t = '[{"id":"complex_detail","params":{"complexId":1},"searchParams":{"tab":"매물"}}]'
    assert decompress_uri(compress_uri(t)) == t
