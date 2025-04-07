# dxf-fix

**dxf-fix** is a Python command-line tool to clean and reconstruct DXF files for photolithography and other precision manufacturing workflows. It flattens arcs and splines into straight segments, snaps nearly-coincident endpoints with micrometer precision, removes duplicate segments, and reconstructs closed, independent shapes using clean `LWPOLYLINE`s.

Many CAD tools export DXF files with curves and loosely connected endpoints, which:
- Prevent proper nesting or shape detection in lithography tools like KLayout
- Cause rendering artifacts or missing features
- Require manual editing to unify and simplify structures

**dxf-fix** automates the cleanup process and ensures your layout geometry is robust and ready for downstream applications.

## Features

- Flattens `LINE`, `ARC`, `CIRCLE`, `POLYLINE`, and `LWPOLYLINE` entities into line segments
- Snaps endpoints using KD-tree clustering with tunable micrometer precision
- Deduplicates symmetric segments (e.g., (A, B) == (B, A))
- Reconstructs independent closed paths from raw segments
- Outputs clean `LWPOLYLINE`s suitable for fabrication and visualization
- Provides a high-resolution debug overlay image to inspect snapping behavior
- Falls back to saving open paths as `LINE`s when closure is not possible

## Installation

Install Python 3.9+ and required packages using pip:

```bash
pip install ezdxf matplotlib scipy
```

### Optional: Create an Isolated Environment with Mamba / Micromamba

If you'd prefer to isolate the dependencies using `mamba` or `micromamba`, you can create and activate an environment like this:

```bash
mamba create -n dxf-fix python=3.10 ezdxf matplotlib scipy
mamba activate dxf-fix
```

Then, run the script as usual:

```bash
python fix_dxf_reconstruct_with_open_paths_fixed.py input.dxf output.dxf
```

## Usage

Run the tool from the command line:

```bash
python fix_dxf_reconstruct_with_open_paths_fixed.py input.dxf output.dxf
```

- `input.dxf`: input DXF file (e.g., exported from Onshape)
- `output.dxf`: cleaned DXF file with reconstructed shapes

You can configure snapping precision and other parameters at the top of the script:

```python
DEFAULT_UNIT = "mm"
DEFAULT_PRECISION_UM = 0.1
DEFAULT_ARC_SEGMENTS = 100
```

## Output

- A cleaned DXF file with closed `LWPOLYLINE`s
- A diagnostic image `snapped_points_overlay.png` visualizing snap effects
- Any open paths that could not be closed will be written as `LINE`s

## License and Attribution

This project is licensed under the BSD 3-Clause License. See the LICENSE file for details.

It has been developed by Tobias Wenzel – Wenzel Lab. If you use this tool in academic work, please consider citing relevant lab publications or linking back to this repository.
