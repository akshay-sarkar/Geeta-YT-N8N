import sys, pathlib, types, json
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))

def test_output_filename_format():
    from fetch_krishna_images import output_filename
    assert output_filename(1) == "001.jpg"
    assert output_filename(42) == "042.jpg"
    assert output_filename(100) == "100.jpg"

def test_search_queries_not_empty():
    from fetch_krishna_images import SEARCH_QUERIES
    assert isinstance(SEARCH_QUERIES, list)
    assert len(SEARCH_QUERIES) >= 3
    assert all(isinstance(q, str) and q.strip() for q in SEARCH_QUERIES)

def test_parse_pexels_photo_url():
    from fetch_krishna_images import parse_photo_url
    photo = {
        "src": {
            "large2x": "https://images.pexels.com/photos/123/pexels-photo-123.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
            "original": "https://images.pexels.com/photos/123/original.jpg"
        }
    }
    url = parse_photo_url(photo)
    assert url.startswith("https://")
    assert "pexels" in url

def test_fetch_images_mock(tmp_path, monkeypatch):
    from fetch_krishna_images import fetch_images
    monkeypatch.chdir(tmp_path)
    (tmp_path / "images" / "krishna-pool").mkdir(parents=True)

    # Mock requests.get for Pexels API call
    search_response = types.SimpleNamespace(
        status_code=200,
        json=lambda: {
            "photos": [
                {"src": {"large2x": "https://example.com/img1.jpg", "original": "https://example.com/img1.jpg"}},
                {"src": {"large2x": "https://example.com/img2.jpg", "original": "https://example.com/img2.jpg"}},
            ],
            "next_page": None,
        },
        raise_for_status=lambda: None,
    )
    # Mock image download response
    image_response = types.SimpleNamespace(
        status_code=200,
        content=b"\xff\xd8\xff\xe0fake-jpeg-bytes",
        raise_for_status=lambda: None,
    )

    call_count = [0]
    def fake_get(url, *args, **kwargs):
        call_count[0] += 1
        if "api.pexels.com" in url:
            return search_response
        return image_response

    import requests
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setenv("PEXELS_API_KEY", "test-api-key")

    count = fetch_images(count=2, output_dir=tmp_path / "images" / "krishna-pool")
    assert count == 2
    files = sorted((tmp_path / "images" / "krishna-pool").iterdir())
    assert len(files) == 2
    assert files[0].name == "001.jpg"
    assert files[1].name == "002.jpg"
