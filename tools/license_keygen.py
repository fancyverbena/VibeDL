"""VibeDL Pro ライセンスキーの発行ツール（販売者専用）。

使い方:
  初回: python tools/license_keygen.py init
        → 鍵ペアを生成し、秘密鍵を license_private_key.txt に保存、
          公開鍵を画面に表示する。公開鍵を src/license_check.py の
          PUBLIC_KEY_B64 に貼ってから exe をビルドすること。
  発行: python tools/license_keygen.py issue --name "購入者名" --email "a@b.c"
        → ライセンスキーを表示する。購入者に渡すのはこのキーだけ。

注意:
  - license_private_key.txt は絶対に Git にコミットしないこと
    （.gitignore 済み）。漏れると誰でもキーを発行できるようになる。
  - 秘密鍵を失くすと既存キーの再発行ができなくなるので、
    パスワードマネージャ等にバックアップすること。
"""
import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from _ed25519_impl import publickey_from_seed, sign  # noqa: E402

PRIVATE_KEY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..",
    "license_private_key.txt")
PRODUCT = "VibeDL Pro"


def _b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def cmd_init(_args):
    if os.path.exists(PRIVATE_KEY_FILE):
        print("既に秘密鍵ファイルがあります:", PRIVATE_KEY_FILE)
        print("上書きしません。作り直す場合は手動で削除してください。")
        return 1
    seed = os.urandom(32)
    with open(PRIVATE_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(_b64(seed) + "\n")
    pub = publickey_from_seed(seed)
    print("秘密鍵を保存しました:", PRIVATE_KEY_FILE)
    print("（このファイルは絶対に公開・コミットしないこと）")
    print()
    print("src/license_check.py の PUBLIC_KEY_B64 に以下を貼ってください:")
    print(f'PUBLIC_KEY_B64 = "{_b64(pub)}"')
    return 0


def _load_seed():
    with open(PRIVATE_KEY_FILE, encoding="utf-8") as f:
        s = f.read().strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def cmd_issue(args):
    seed = _load_seed()
    payload = {
        "product": PRODUCT,
        "name": args.name,
        "email": args.email,
        "issued": date.today().isoformat(),
        "edition": "pro",
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")
    blob = payload_bytes + sign(seed, payload_bytes)
    # 区切り文字 '-' と衝突しない base32 で符号化する
    raw = base64.b32encode(blob).decode().rstrip("=")
    key = "-".join(raw[i:i + 5] for i in range(0, len(raw), 5))
    print("ライセンスキー（購入者に渡す）:")
    print(key)
    return 0


def main():
    parser = argparse.ArgumentParser(description="VibeDL Pro キー発行ツール")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="鍵ペアを初期生成する")
    p_issue = sub.add_parser("issue", help="ライセンスキーを発行する")
    p_issue.add_argument("--name", required=True, help="購入者名")
    p_issue.add_argument("--email", default="", help="購入者メールアドレス")
    args = parser.parse_args()
    if args.cmd == "init":
        return cmd_init(args)
    return cmd_issue(args)


if __name__ == "__main__":
    sys.exit(main())
