"""Ed25519 の署名・検証（純 Python 実装、RFC 8032 準拠）。

外部依存を増やさないため、ライセンスキーに必要な範囲だけを実装している。
アプリ側は検証のみ使用する。署名には秘密鍵（シード）が別途必要で、
このモジュール自体に秘密情報は含まれない。
"""
import hashlib

_q = 2 ** 255 - 19
_l = 2 ** 252 + 27742317777372353535851937790883648493


def _H(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, _q - 2, _q)


_d = -121665 * _inv(121666) % _q
_I = pow(2, (_q - 1) // 4, _q)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_d * y * y + 1) % _q
    x = pow(xx, (_q + 3) // 8, _q)
    if (x * x - xx) % _q != 0:
        x = (x * _I) % _q
    if x % 2 != 0:
        x = _q - x
    return x


_By = 4 * _inv(5) % _q
_B = [_xrecover(_By), _By]


def _edwards(P, Q):
    x1, y1 = P
    x2, y2 = Q
    t = _d * x1 * x2 * y1 * y2 % _q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + t) % _q
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - t) % _q
    return [x3, y3]


def _scalarmult(P, e):
    if e == 0:
        return [0, 1]
    Q = _scalarmult(P, e // 2)
    Q = _edwards(Q, Q)
    if e & 1:
        Q = _edwards(Q, P)
    return Q


def _encodepoint(P):
    x, y = P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decodepoint(s):
    y = int.from_bytes(s, "little") & (2 ** 255 - 1)
    sign = (s[31] >> 7) & 1
    x = _xrecover(y)
    if (x & 1) != sign:
        x = _q - x
    return [x, y]


def _clamp(h32):
    a = int.from_bytes(h32, "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a


def publickey_from_seed(seed):
    """32バイトのシードから公開鍵（32バイト）を導出する。"""
    h = _H(seed)
    a = _clamp(h[:32])
    return _encodepoint(_scalarmult(_B, a))


def sign(seed, message):
    """シード（秘密鍵）で message に署名し、64バイトの署名を返す。"""
    h = _H(seed)
    a = _clamp(h[:32])
    prefix = h[32:]
    A = _encodepoint(_scalarmult(_B, a))
    r = int.from_bytes(_H(prefix + message), "little") % _l
    R = _encodepoint(_scalarmult(_B, r))
    k = int.from_bytes(_H(R + A + message), "little") % _l
    S = (r + k * a) % _l
    return R + S.to_bytes(32, "little")


def verify(public_key, message, signature):
    """署名を検証する。形式不正や不一致は False。"""
    if len(public_key) != 32 or len(signature) != 64:
        return False
    try:
        A = _decodepoint(public_key)
        R = _decodepoint(signature[:32])
    except Exception:
        return False
    S = int.from_bytes(signature[32:], "little")
    if S >= _l:
        return False
    k = int.from_bytes(_H(signature[:32] + public_key + message),
                       "little") % _l
    return _scalarmult(_B, S) == _edwards(R, _scalarmult(A, k))
