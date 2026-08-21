import qrcode
from qrcode.image.svg import SvgPathImage


def build_qr_svg(data):
    qr = qrcode.QRCode(
        box_size=10,
        border=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(image_factory=SvgPathImage).to_string(encoding="unicode")
