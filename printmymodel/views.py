import textalloc as ta
import re
import numpy as np
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.conf import settings
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from io import BytesIO
from django.core.files.storage import FileSystemStorage

# z-axis : 58.75
# bean : 76


def remove_lines_containing_page_no_and_blank(lines):
    filtered_lines = [
        line for line in lines if "PAGE NO" not in line and line.strip() != ""
    ]
    return filtered_lines


def strip_initial_numbering(line):
    return re.sub(r"^\s*\d+\.\s+", "", line)


@login_required
def get_frame_details(request):
    if request.method == "POST":
        anl_file = request.FILES.get("anl_file")
        if anl_file:
            if not anl_file.name.lower().endswith(".anl"):
                return render(
                    request,
                    "printmymodel/file_upload_success.html",
                    {
                        "status": "error",
                        "message": "Invalid file type. Only .anl files are allowed.",
                    },
                )

            fs = FileSystemStorage(location=settings.MODEL_DIR)
            filename = fs.save(anl_file.name, anl_file)
            file_path = fs.path(filename)

            for encoding in ["utf-8", "latin-1", "cp1252"]:
                try:
                    with open(file_path, "r", encoding=encoding) as file:
                        read_line = file.readlines()
                    break
                except UnicodeDecodeError:
                    continue

            lines = remove_lines_containing_page_no_and_blank(read_line)
            lines = [strip_initial_numbering(line) for line in lines]

            extracted_members = extract_members_and_nodes(lines)
            member_dimension = extract_member_dimensions(lines)

            member_properties_multiplied = {}
            for member, dimensions in member_dimension.items():
                if isinstance(dimensions, tuple):
                    member_properties_multiplied[member] = tuple(
                        int(d * 1000) for d in dimensions
                    )
                else:
                    member_properties_multiplied[member] = dimensions

            node_coordinates = extract_joint_coordinates(lines)
            coordinate_type = request.POST.get("coordinate_type")
            coordinate_value = request.POST.get("coordinate_value")
            if coordinate_value:
                coordinate_value = float(coordinate_value)
            else:
                return render(
                    request,
                    "printmymodel/file_upload_success.html",
                    {"status": "error", "message": "No coordinate provided"},
                )
            # x_list = json.loads(request.POST.get('x_list', '[]'))
            # z_list = json.loads(request.POST.get('z_list', '[]'))

            # Filter members based on coordinate type and value
            filtered_members = []
            for member in extracted_members:
                member_no, bottom_joint, top_joint = member
                bottom_coord = node_coordinates[bottom_joint]
                top_coord = node_coordinates[top_joint]

                if coordinate_type == "X" and (
                    round(bottom_coord[0], 2) == round(coordinate_value, 2)
                    and round(top_coord[0], 2) == round(coordinate_value, 2)
                ):
                    filtered_members.append(member)
                elif coordinate_type == "Z" and (
                    round(bottom_coord[2], 2) == round(coordinate_value, 2)
                    and round(top_coord[2], 2) == round(coordinate_value, 2)
                ):
                    filtered_members.append(member)

            fig, ax = draw_frame(
                filtered_members, node_coordinates, member_properties_multiplied
            )

            # Save the figure to a BytesIO object as SVG
            buffer = BytesIO()
            fig.savefig(buffer, format="svg")
            buffer.seek(0)
            svg_data = buffer.getvalue().decode("utf-8")

            return render(
                request,
                "printmymodel/file_upload_success.html",
                {
                    "svg_data": svg_data,
                    "status": "success",
                    "message": "Model successfully read. Here is the generated image",
                    "filtered_members": filtered_members,
                    "node_coordinates": node_coordinates,
                    "member_properties_multiplied": member_properties_multiplied,
                },
            )

    return render(request, "printmymodel/frame_details.html")


def extract_members_and_nodes(lines):
    in_member_incidences = False
    member_incidences = []

    for line in lines:
        stripped_line = line.strip()

        if "MEMBER INCIDENCES" in stripped_line:
            in_member_incidences = True
            continue

        if in_member_incidences:
            if stripped_line and not stripped_line.split(" ")[0].isdigit():
                break

            parts = stripped_line.split(";")
            for part in parts:
                if part.strip():
                    member_data = part.strip().split()
                    member_incidences.append(member_data)

    return member_incidences


def expand_ranges(line):
    parts = line.split()
    expanded_parts = []
    i = 0
    while i < len(parts):
        if parts[i] == "TO":
            start = int(parts[i - 1])
            end = int(parts[i + 1])
            expanded_parts.extend(range(start + 1, end + 1))
            i += 2
        else:
            expanded_parts.append(parts[i])
            i += 1
    return " ".join(map(str, expanded_parts))


def preprocess_line(line, previous_line):
    stripped_line = line.strip()
    # Merge lines ending with '-'
    if stripped_line.endswith("-"):
        merged_line = previous_line + stripped_line[:-1].strip() + " "
        return merged_line, True
    else:
        merged_line = previous_line + stripped_line
        # Expand ranges containing 'TO'
        if " TO " in merged_line:
            merged_line = expand_ranges(merged_line)
        return merged_line, False


def expand_ranges(line):
    parts = line.split()
    expanded_parts = []
    i = 0
    while i < len(parts):
        if parts[i] == "TO":
            start = int(parts[i - 1])
            end = int(parts[i + 1])
            expanded_parts.extend(range(start + 1, end + 1))
            i += 2
        else:
            expanded_parts.append(parts[i])
            i += 1
    return " ".join(map(str, expanded_parts))


def preprocess_line(line, previous_line):
    stripped_line = line.strip()
    # Merge lines ending with '-'
    if stripped_line.endswith("-"):
        merged_line = previous_line + stripped_line[:-1].strip() + " "
        return merged_line, True
    else:
        merged_line = previous_line + stripped_line
        # Expand ranges containing 'TO'
        if " TO " in merged_line:
            merged_line = expand_ranges(merged_line)
        return merged_line, False


def extract_member_dimensions(lines):
    in_member_property = False
    member_properties = {}
    current_line_index = 0
    previous_line = ""

    while current_line_index < len(lines):
        line = lines[current_line_index]
        stripped_line = line.strip()

        if "MEMBER PROPERTY" in stripped_line:
            in_member_property = True
            current_line_index += 1
            continue

        if in_member_property:
            # Preprocess the line (merge, strip numbering, expand ranges)
            stripped_line, continue_flag = preprocess_line(line, previous_line)
            if continue_flag:
                previous_line = stripped_line
                current_line_index += 1
                continue
            previous_line = ""

            if (
                "*---------------------------------------------------------------------------*"
                in stripped_line
                or "CONSTANTS" in stripped_line
            ):
                break
            if "*" in stripped_line:
                current_line_index += 1
                continue

            parts = stripped_line.split(" ")
            property_data = []
            members = []
            dimensions_start = False
            table_mode = False
            table_data = ""

            for part in parts:
                if part.isdigit():
                    members.append(part)
                elif part == "TABLE":
                    table_mode = True
                else:
                    if table_mode:
                        table_data += part + " "
                    else:
                        dimensions_start = True
                        property_data.append(part)

            if table_mode:
                members = [int(member) for member in members]
                table_data = table_data.strip()
                for member in members:
                    member_properties[member] = table_data
            elif dimensions_start:
                members = [int(member) for member in members]
                # Handle TAPERED and other cases
                if "TAPERED" in property_data:
                    property_data.remove("TAPERED")
                # Adjust property data to ensure there are seven elements
                if len(property_data) == 5:
                    property_data.insert(5, property_data[3])
                    property_data.insert(6, property_data[4])
                dimensions = tuple(map(float, property_data))
                for member in members:
                    member_properties[member] = dimensions

        current_line_index += 1

    return member_properties


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def extract_joint_coordinates(lines):
    in_joint_coordinates = False
    joint_coordinates = {}

    for line in lines:
        stripped_line = line.strip()

        if "JOINT COORDINATES" in stripped_line:
            in_joint_coordinates = True
            continue

        if in_joint_coordinates:
            if stripped_line and not is_number(stripped_line.split(" ")[0]):
                break
            parts = stripped_line.split(";")
            for part in parts:
                if part.strip():
                    joint_data = part.strip().split()
                    joint_name = joint_data[0]
                    x_coord = float(joint_data[1])
                    y_coord = float(joint_data[2])
                    z_coord = float(joint_data[3])
                    joint_coordinates[joint_name] = (x_coord, y_coord, z_coord)

    return joint_coordinates


def format_dimension_label(dimensions):
    if isinstance(dimensions, tuple):
        of = f"OF- {int(dimensions[3])}X{int(dimensions[4])}"
        web = f"WEB- {int(dimensions[1])}thk."
        if_ = f"IF- {int(dimensions[5])}X{int(dimensions[6])}"
        return f"{of}\n{web}\n{if_}"
    else:
        return dimensions


def write_member_dimensions_to_file(member_properties, output_file_path):
    with open(output_file_path, "w") as file:
        for member, dimensions in sorted(member_properties.items()):
            dimensions_str = " ".join(map(str, dimensions))
            file.write(f"{dimensions_str}\n")


def draw_frame(members_and_nodes, node_coordinates, member_dimension):
    fig, ax = plt.subplots(figsize=(16.5, 11.7))

    x_values = []
    y_values = []
    dimension_labels = []

    for member in members_and_nodes:
        member_no, bottom_joint, top_joint = member
        x1, y1, z1 = node_coordinates[bottom_joint]
        x2, y2, z2 = node_coordinates[top_joint]

        length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)

        x_values.extend([x1, x2])
        y_values.extend([y1, y2])
        ax.plot([x1, x2], [y1, y2], "o-", color="#a9a9a9")

        dimensions = member_dimension.get(int(member_no))
        if dimensions:
            dimension_label = format_dimension_label(dimensions)
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2


            if isinstance(dimensions, tuple):
                bottom_end_value = dimensions[0] - dimensions[4] - dimensions[6]
                top_end_value = dimensions[2] - dimensions[4] - dimensions[6]

                # ax.text(x1, y1 + 0.14, f"↓{bottom_end_value}", fontsize=5, color="blue", ha="center", va="center")
                # ax.text(x2, y2 - 0.14, f"↑{top_end_value}", fontsize=5, color="blue", ha="center", va="center")

            dimension_labels.append((mid_x, mid_y, f"{dimension_label}\n⟷{length:.3f}\n↑{top_end_value}\n↓{bottom_end_value}"))

    # Allocate dimension labels
    ta.allocate(
        ax,
        [t[0] for t in dimension_labels],
        [t[1] for t in dimension_labels],
        [t[2] for t in dimension_labels],
        textsize=5,
        textcolor="yellow",
        linecolor="k",
        linewidth=0.4,
        # direction="northeast",
        bbox=dict(
            facecolor="black", alpha=0.7, edgecolor="none", boxstyle="round,pad=0.1"
        ),
    )

    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title("Sections properties")
    ax.grid(False)
    ax.legend().set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    return fig, ax

# def draw_frame(members_and_nodes, node_coordinates, member_dimension):
#     fig, ax = plt.subplots(figsize=(16.5, 11.7))
#     # fig, ax = plt.subplots(figsize=(12, 10))

#     x_values = []
#     y_values = []
#     text_list = []

#     for member in members_and_nodes:
#         member_no, bottom_joint, top_joint = member
#         x1, y1, z1 = node_coordinates[bottom_joint]
#         x2, y2, z2 = node_coordinates[top_joint]

#         length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)

#         x_values.extend([x1, x2])
#         y_values.extend([y1, y2])
#         ax.plot([x1, x2], [y1, y2], "o-", color="#a9a9a9", label=f"Member {member_no}")

#         dimensions = member_dimension.get(int(member_no))
#         if dimensions:
#             dimension_label = format_dimension_label(dimensions)
#             mid_x = (x1 + x2) / 2
#             mid_y = (y1 + y2) / 2

#             text_list.append((mid_x, mid_y, dimension_label))
#             text_list.append((mid_x, mid_y + 0.1, f"{member_no}"))

#             if isinstance(dimensions, tuple):
#                 bottom_end_value = dimensions[0] - dimensions[4] - dimensions[6]
#                 top_end_value = dimensions[2] - dimensions[4] - dimensions[6]

#             text_list.append((x1, y1 + 0.14, f"{bottom_end_value}"))
#             text_list.append((x2, y2 - 0.14, f"{top_end_value}"))

#     for x, y, text in text_list:
#         ax.text(x, y, text, fontsize=5, color="blue", ha="center", va="center")

#     ta.allocate(
#         ax,
#         [t[0] for t in text_list],
#         [t[1] for t in text_list],
#         [t[2] for t in text_list],
#         textsize=5,
#         textcolor="#f5f10f",
#         linecolor="k",
#         linewidth=0.4,
#         direction="northeast",
#         bbox=dict(
#             facecolor="black", alpha=0.6, edgecolor="none", boxstyle="round,pad=0.05"
#         ),
#     )

#     ax.set_xlabel("")
#     ax.set_ylabel("")
#     ax.set_title("Sections properties")
#     ax.grid(False)
#     ax.legend().set_visible(False)
#     ax.set_xticks([])
#     ax.set_yticks([])

#     return fig, ax
