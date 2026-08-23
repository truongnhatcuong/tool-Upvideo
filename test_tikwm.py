import requests

def test_tikwm(url):
    print(f"Testing URL: {url}")
    try:
        response = requests.post("https://www.tikwm.com/api/", data={"url": url})
        response.raise_for_status()
        data = response.json()
        if data.get("code") == 0:
            print("Success!")
            info = data.get("data", {})
            print("Title:", info.get("title"))
            print("Play URL:", info.get("play"))
            print("No watermark play URL:", info.get("hdplay") or info.get("play"))
        else:
            print("Failed:", data)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_tikwm("https://www.tiktok.com/@caubatapchoigame/video/7674821736168164629")
