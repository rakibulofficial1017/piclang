from PIL import Image
from typing import List, Tuple, cast


RGB = Tuple[int, int, int]
Row = List[RGB]
Grid2D = List[Row]

def image_to_rgb_2d_array(image_path: str) -> Grid2D:
    """
    Opens an image file and converts it into a 2D array of RGB tuples.
    Silences Pillow 14 deprecation warnings by using get_flattened_data.
    """
    with Image.open(image_path) as img:
        rgb_img = img.convert("RGB")
        width, height = rgb_img.size
        
        # FIX: Replaced rgb_img.getdata() with get_flattened_data()
        # It natively returns a tuple of pixel values, perfect for casting
        flat_pixels = cast(List[RGB], rgb_img.get_flattened_data())
        
        # Reconstruct the flat tuple into a 2D array (list of rows)
        grid_2d: Grid2D = [
            list(flat_pixels[i * width : (i + 1) * width]) 
            for i in range(height)
        ]
        
        return grid_2d
    
def rgb_2d_array_to_image(grid: Grid2D, output_path: str) -> None:
    height = len(grid)
    if height == 0:
        raise ValueError("The 2D array cannot be empty.")
    width = len(grid[0])
    if width == 0:
        raise ValueError("Rows in the 2D array cannot be empty.")
    flat_pixels = cast(List[RGB], [pixel for row in grid for pixel in row])
    img = Image.new("RGB", (width, height))
    img.putdata(flat_pixels)
    img.save(output_path)
    print(f"Successfully saved image to {output_path} ({width}x{height})")
    


v = image_to_rgb_2d_array("./script.jpg")

print("\n".join(["".join([f"\033[38;2;{i[0]};{i[1]};{i[2]}m██\033[0m" for i in j]) for j in v]))