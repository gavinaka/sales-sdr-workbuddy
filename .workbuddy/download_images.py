import urllib.request
import os

images = [
    ("c8KimKU66Tz16TWZ.png", "https://uploader.shimo.im/f/c8KimKU66Tz16TWZ.png!thumbnail?accessToken=eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3ODE5NjU2OTEsImZpbGVHVUlEIjoiTXhoc3Q3UnJRcXJnampTbSIsImlhdCI6MTc4MTk2NTM5MSwiaXNzIjoidXBsb2FkZXJfYWNjZXNzX3Jlc291cmNlIiwicGFhIjoiYWxsOmFsbDoiLCJ1c2VySWQiOjQyNzg3MDIyfQ.T_WW0G1HkslDdWgsKq9iVgbDh6iLiKEvw_hV-Ay2GcE"),
    ("5336l9qJ48PsvHKC.png", "https://uploader.shimo.im/f/5336l9qJ48PsvHKC.png!thumbnail?accessToken=eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3ODE5NjU2OTEsImZpbGVHVUlEIjoiTXhoc3Q3UnJRcXJnampTbSIsImlhdCI6MTc4MTk2NTM5MSwiaXNzIjoidXBsb2FkZXJfYWNjZXNzX3Jlc291cmNlIiwicGFhIjoiYWxsOmFsbDoiLCJ1c2VySWQiOjQyNzg3MDIyfQ.T_WW0G1HkslDdWgsKq9iVgbDh6iLiKEvw_hV-Ay2GcE"),
    ("Ee33rzPKGqOjaPzQ.png", "https://uploader.shimo.im/f/Ee33rzPKGqOjaPzQ.png!thumbnail?accessToken=eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3ODE5NjU2OTEsImZpbGVHVUlEIjoiTXhoc3Q3UnJRcXJnampTbSIsImlhdCI6MTc4MTk2NTM5MSwiaXNzIjoidXBsb2FkZXJfYWNjZXNzX3Jlc291cmNlIiwicGFhIjoiYWxsOmFsbDoiLCJ1c2VySWQiOjQyNzg3MDIyfQ.T_WW0G1HkslDdWgsKq9iVgbDh6iLiKEvw_hV-Ay2GcE"),
    ("gFApvVw4t5f2GcwG.png", "https://uploader.shimo.im/f/gFApvVw4t5f2GcwG.png!thumbnail?accessToken=eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3ODE5NjU2OTEsImZpbGVHVUlEIjoiTXhoc3Q3UnJRcXJnampTbSIsImlhdCI6MTc4MTk2NTM5MSwiaXNzIjoidXBsb2FkZXJfYWNjZXNzX3Jlc291cmNlIiwicGFhIjoiYWxsOmFsbDoiLCJ1c2VySWQiOjQyNzg3MDIyfQ.T_WW0G1HkslDdWgsKq9iVgbDh6iLiKEvw_hV-Ay2GcE"),
    ("g0hRVNsOMrykYRB0.png", "https://uploader.shimo.im/f/g0hRVNsOMrykYRB0.png!thumbnail?accessToken=eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3ODE5NjU2OTEsImZpbGVHVUlEIjoiTXhoc3Q3UnJRcXJnampTbSIsImlhdCI6MTc4MTk2NTM5MSwiaXNzIjoidXBsb2FkZXJfYWNjZXNzX3Jlc291cmNlIiwicGFhIjoiYWxsOmFsbDoiLCJ1c2VySWQiOjQyNzg3MDIyfQ.T_WW0G1HkslDdWgsKq9iVgbDh6iLiKEvw_hV-Ay2GcE"),
    ("MzWK5i1wCNZbXwCL.png", "https://uploader.shimo.im/f/MzWK5i1wCNZbXwCL.png!thumbnail?accessToken=eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3ODE5NjU2OTEsImZpbGVHVUlEIjoiTXhoc3Q3UnJRcXJnampTbSIsImlhdCI6MTc4MTk2NTM5MSwiaXNzIjoidXBsb2FkZXJfYWNjZXNzX3Jlc291cmNlIiwicGFhIjoiYWxsOmFsbDoiLCJ1c2VySWQiOjQyNzg3MDIyfQ.T_WW0G1HkslDdWgsKq9iVgbDh6iLiKEvw_hV-Ay2GcE"),
    ("aJGvEh0BEftBJGjY.png", "https://uploader.shimo.im/f/aJGvEh0BEftBJGjY.png!thumbnail?accessToken=eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3ODE5NjU2OTEsImZpbGVHVUlEIjoiTXhoc3Q3UnJRcXJnampTbSIsImlhdCI6MTc4MTk2NTM5MSwiaXNzIjoidXBsb2FkZXJfYWNjZXNzX3Jlc291cmNlIiwicGFhIjoiYWxsOmFsbDoiLCJ1c2VySWQiOjQyNzg3MDIyfQ.T_WW0G1HkslDdWgsKq9iVgbDh6iLiKEvw_hV-Ay2GcE"),
    ("SL29aIoUbWiT6xaY.png", "https://uploader.shimo.im/f/SL29aIoUbWiT6xaY.png!thumbnail?accessToken=eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3ODE5NjU2OTEsImZpbGVHVUlEIjoiTXhoc3Q3UnJRcXJnampTbSIsImlhdCI6MTc4MTk2NTM5MSwiaXNzIjoidXBsb2FkZXJfYWNjZXNzX3Jlc291cmNlIiwicGFhIjoiYWxsOmFsbDoiLCJ1c2VySWQiOjQyNzg3MDIyfQ.T_WW0G1HkslDdWgsKq9iVgbDh6iLiKEvw_hV-Ay2GcE"),
    ("DK1Fz5z7mPHaAp3N.png", "https://uploader.shimo.im/f/DK1Fz5z7mPHaAp3N.png!thumbnail?accessToken=eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ.eyJleHAiOjE3ODE5NjU2OTEsImZpbGVHVUlEIjoiTXhoc3Q3UnJRcXJnampTbSIsImlhdCI6MTc4MTk2NTM5MSwiaXNzIjoidXBsb2FkZXJfYWNjZXNzX3Jlc291cmNlIiwicGFhIjoiYWxsOmFsbDoiLCJ1c2VySWQiOjQyNzg3MDIyfQ.T_WW0G1HkslDdWgsKq9iVgbDh6iLiKEvw_hV-Ay2GcE"),
]

out_dir = r"D:/Git/销售SDR/.workbuddy/meeting_images"
os.makedirs(out_dir, exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://shimo.im/",
}

results = []
for fname, url in images:
    fpath = os.path.join(out_dir, fname)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(fpath, "wb") as f:
                f.write(data)
        size = len(data)
        results.append(f"✅ {fname} ({size/1024:.1f}KB)")
    except Exception as e:
        results.append(f"❌ {fname}: {e}")

print("\n".join(results))
print(f"\n下载目录: {out_dir}")
