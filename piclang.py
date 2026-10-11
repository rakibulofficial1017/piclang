
import argparse
import base64
import json
import math
import struct
import zlib
from pathlib import Path

from PIL import Image


MAGIC = b"IMGCODEC"
HEADER_FORMAT = ">8sBQQ"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

TYPE_FILE = 0
TYPE_FOLDER = 1

DEFAULT_WIDTH = None


def folder_to_dict(folder: Path) -> dict:
    """Serialize a folder recursively, preserving binary file contents."""
    result = {}

    for path in sorted(folder.iterdir()):
        if path.is_symlink():
            continue

        if path.is_dir():
            result[path.name] = folder_to_dict(path)
        elif path.is_file():
            result[path.name] = base64.b64encode(
                path.read_bytes()
            ).decode("ascii")

    return result


def dict_to_folder(data: dict, folder: Path) -> None:
    """Recreate a folder recursively from its serialized representation."""
    folder.mkdir(parents=True, exist_ok=True)

    for name, content in data.items():
        # Prevent paths from escaping the output directory.
        if (
            not isinstance(name, str)
            or name in ("", ".", "..")
            or "/" in name
            or "\\" in name
            or "\0" in name
        ):
            raise ValueError(f"Invalid filename in archive: {name!r}")

        path = folder / name

        if isinstance(content, dict):
            dict_to_folder(content, path)
        elif isinstance(content, str):
            path.write_bytes(base64.b64decode(content, validate=True))
        else:
            raise ValueError(f"Invalid archive entry: {name!r}")


def encode_path(
    input_path: str,
    output_path: str | None = None,
    width: int | None = DEFAULT_WIDTH,
) -> None:
    source = Path(input_path)

    if not source.exists():
        raise FileNotFoundError(f"Input does not exist: {source}")

    if source.is_symlink():
        raise ValueError("Symbolic links cannot be encoded directly.")

    if output_path is None:
        output_path = str(source) + ".png"

    if width is not None and width < 1:
        raise ValueError("Width must be at least 1 pixel.")

    if source.is_dir():
        payload_data = json.dumps(
            {source.name: folder_to_dict(source)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        data_type = TYPE_FOLDER
    else:
        payload_data = source.read_bytes()
        data_type = TYPE_FILE

    compressed_data = zlib.compress(payload_data)

    header = struct.pack(
        HEADER_FORMAT,
        MAGIC,
        data_type,
        len(payload_data),
        len(compressed_data),
    )

    payload = header + compressed_data

    # Three bytes are stored in each RGB pixel.
    pixel_count = (len(payload) + 2) // 3

    if width is None:
        # Smallest integer width that produces a near-square image.
        width = math.isqrt(pixel_count - 1) + 1

    height = (pixel_count + width - 1) // width
    image_byte_count = width * height * 3

    payload += bytes(image_byte_count - len(payload))

    pixels = [
        tuple(payload[i:i + 3])
        for i in range(0, len(payload), 3)
    ]

    image = Image.new("RGB", (width, height))
    image.putdata(pixels)
    image.save(output_path, format="PNG")

    print(f"Encoded: {source} -> {output_path}")
    print(f"Type: {'folder' if data_type == TYPE_FOLDER else 'file'}")
    print(f"Original size:   {len(payload_data):,} bytes")
    print(f"Compressed size: {len(compressed_data):,} bytes")
    print(f"Compressed size: {1-len(compressed_data)/len(payload_data):.4%} bytes")
    print(f"Image size:      {width}x{height}")


def decode_path(
    input_path: str,
    output_path: str | None = None,
) -> None:
    source = Path(input_path)

    with Image.open(source) as image:
        image = image.convert("RGB")
        data = bytes(
            channel
            for pixel in image.get_flattened_data()
            for channel in pixel
        )

    if len(data) < HEADER_SIZE:
        raise ValueError("Image is too small to contain a valid header.")

    magic, data_type, original_size, compressed_size = struct.unpack(
        HEADER_FORMAT,
        data[:HEADER_SIZE],
    )

    if magic != MAGIC:
        raise ValueError("Invalid image format or missing IMGCODEC header.")

    if data_type not in (TYPE_FILE, TYPE_FOLDER):
        raise ValueError("Unknown encoded data type.")

    end = HEADER_SIZE + compressed_size

    if end > len(data):
        raise ValueError("Image is incomplete or corrupted.")

    restored_data = zlib.decompress(data[HEADER_SIZE:end])

    if len(restored_data) != original_size:
        raise ValueError("Decoded size does not match the header.")

    if data_type == TYPE_FILE:
        if output_path is None:
            output_path = str(source.with_suffix(""))

        Path(output_path).write_bytes(restored_data)
        print(f"Decoded file: {output_path}")

    else:
        archive = json.loads(restored_data.decode("utf-8"))

        if not isinstance(archive, dict) or len(archive) != 1:
            raise ValueError("Invalid folder archive.")

        folder_name, contents = next(iter(archive.items()))

        if (
            not isinstance(folder_name, str)
            or folder_name in ("", ".", "..")
            or "/" in folder_name
            or "\\" in folder_name
            or "\0" in folder_name
            or not isinstance(contents, dict)
        ):
            raise ValueError("Invalid folder archive structure.")

        destination = Path(output_path) if output_path else Path(folder_name)
        dict_to_folder(contents, destination)

        print(f"Decoded folder: {destination}")

    print(f"Restored size: {len(restored_data):,} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Encode files and folders into PNG images."
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    enc = subparsers.add_parser(
        "encode",
        help="Encode a file or folder into PNG.",
    )
    enc.add_argument("input", help="Input file or folder")
    enc.add_argument("-o", "--output", help="Output PNG path")
    enc.add_argument(
        "-w", "--width",
        type=int,
        default=None,
        help="Image width (default: automatically choose a near-square image)",
    )

    dec = subparsers.add_parser(
        "decode",
        help="Restore a file or folder from PNG.",
    )
    dec.add_argument("input", help="Encoded PNG image")
    dec.add_argument(
        "-o", "--output",
        help="Output file path or folder path",
    )

    args = parser.parse_args()

    try:
        if args.command == "encode":
            encode_path(args.input, args.output, args.width)
        else:
            decode_path(args.input, args.output)
    except (
        OSError,
        ValueError,
        zlib.error,
        struct.error,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
