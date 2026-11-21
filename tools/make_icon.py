"""exe 用アイコン (assets/icon.ico) を生成する。

アプリ内アイコンと同じバイオレット基調で、角丸スクエアに白い
音符を描く。ビルド時に build.bat から呼ばれる。
"""
import os

from PIL import Image, ImageDraw

SIZE = 256
VIOLET = (124, 92, 255, 255)
WHITE = (255, 255, 255, 255)


def draw_icon():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 角丸スクエア
    d.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=52, fill=VIOLET)

    # 八分音符（符幹＋旗＋符頭2つ）
    d.rectangle([168, 62, 182, 168], fill=WHITE)          # 符幹
    d.polygon([(168, 62), (222, 84), (222, 128), (168, 106)],
              fill=WHITE)                                  # 旗
    d.ellipse([128, 150, 184, 192], fill=WHITE)            # 符頭（右）
    d.rectangle([104, 84, 118, 190], fill=WHITE)           # 符幹2
    d.ellipse([64, 172, 120, 214], fill=WHITE)             # 符頭（左）

    return img


def main():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "assets")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "icon.ico")
    img = draw_icon()
    img.save(out_path, format="ICO",
             sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                    (128, 128), (256, 256)])
    print(f"アイコンを生成しました: {out_path}")


if __name__ == "__main__":
    main()
