import easyocr
import requests

reader = easyocr.Reader(["en", "bn"], gpu=False)


def extract_text_from_url(image_url):
    print("Image URL:", image_url)

    response = requests.get(image_url, timeout=30)
    response.raise_for_status()

    print("Status Code:", response.status_code)
    print("Image Size:", len(response.content), "bytes")

    # Save image for debugging
    with open("debug_kyc.jpg", "wb") as f:
        f.write(response.content)

    print("Image saved as debug_kyc.jpg")

    result = reader.readtext("debug_kyc.jpg", detail=1)

    print("\n===== RAW OCR RESULT =====")
    print(result)
    print("==========================\n")

    text = " ".join(item[1] for item in result)

    return text