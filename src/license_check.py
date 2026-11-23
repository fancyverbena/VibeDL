"""VibeDL Pro ライセンスキーの検証。

キー形式: ペイロード(JSON) + Ed25519署名(64バイト) を base32 化し、
5文字ごとに '-' で区切った文字列。検証は同梱の公開鍵で行う（オフライン）。
（base64 系は '-' 自体が文字集合に含まれるため区切りに使えず、base32 を使う）

注意: 現在の PUBLIC_KEY_B64 は開発用テスト鍵。
販売前に tools/license_keygen.py init で本番鍵ペアを生成し、
この公開鍵を差し替えてから exe をビルドすること。
"""
import base64
import json

from _ed25519_impl import verify as _ed25519_verify

PUBLIC_KEY_B64 = "lJLf8Kjgog65O8TASU0aQqOY_leOc-GOQd9C6TCawek"
PRODUCT = "VibeDL Pro"


def _b64decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def parse_license_key(key):
    """キーを検証し、ペイロード dict を返す。無効なら None。"""
    if not key:
        return None
    try:
        raw = "".join(key.split()).replace("-", "").upper()
        blob = base64.b32decode(raw + "=" * (-len(raw) % 8))
        if len(blob) <= 64:
            return None
        payload_bytes, signature = blob[:-64], blob[-64:]
        public_key = _b64decode(PUBLIC_KEY_B64)
        if not _ed25519_verify(public_key, payload_bytes, signature):
            return None
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("product") != PRODUCT or payload.get("edition") != "pro":
        return None
    return payload


def is_pro(key):
    """保存されたライセンスキーが有効な Pro かどうか。"""
    return parse_license_key(key) is not None
