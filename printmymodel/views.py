import json
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

            with open(file_path, "r") as file:
                lines = file.readlines()

            extracted_members = extract_members_and_nodes(lines)
            member_dimension = extract_member_dimensions(lines)
            member_properties_multiplied = {}
            for member, dimensions in member_dimension.items():
                member_properties_multiplied[member] = tuple(
                    int(dim * 1000) for dim in dimensions
                )
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

            # print(filtered_members)
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
            if "PAGE NO." in stripped_line:
                continue

            if stripped_line and not stripped_line.split(" ")[1].isdigit():
                break
            stripped_line = " ".join(stripped_line.split(" ")[1:])
            parts = stripped_line.split(";")
            for part in parts:
                if part.strip():
                    member_data = part.strip().split()
                    member_incidences.append(member_data)

    return member_incidences


def extract_member_dimensions(lines):
    in_member_property = False
    member_properties = {}

    current_line_index = 0

    while current_line_index < len(lines):
        line = lines[current_line_index]
        stripped_line = line.strip()

        if "MEMBER PROPERTY" in stripped_line:
            in_member_property = True
            current_line_index += 1
            continue

        if in_member_property:
            if "PAGE NO." in stripped_line or not line.strip():
                current_line_index += 1
                continue

            if (
                "*---------------------------------------------------------------------------*"
                in line or 'CONSTANTS' in line
            ):
                break

            if "TABLE" in stripped_line or '*' in stripped_line:
                current_line_index += 1
                continue

            if stripped_line.endswith("-"):
                combined_line = stripped_line[:-1].strip()
                next_line_index = current_line_index + 1
                while next_line_index < len(lines):
                    next_line = lines[next_line_index].strip()
                    if next_line.endswith("-"):
                        combined_line += " " + next_line[:-1].strip()
                        next_line_index += 1
                    elif "TABLE" in next_line:
                        current_line_index = next_line_index + 1
                        break
                    else:
                        combined_line += " " + " ".join(next_line.split()[1:])
                        current_line_index = next_line_index
                        break
                stripped_line = combined_line

            if "TABLE" in stripped_line:
                current_line_index += 1
                continue

            stripped_line = " ".join(stripped_line.split(" ")[1:])
            parts = stripped_line.split(" ")
            property_data = []
            members = []
            dimensions_start = False
            for part in parts:
                if part.isdigit() or (part == "TO"):
                    members.append(part)
                else:
                    if part != "TAPERED":
                        dimensions_start = True
                        property_data.append(part)

            if dimensions_start:
                if "TO" in members:
                    expanded_members = []
                    i = 0
                    while i < len(members):
                        if members[i] == "TO":
                            start = int(members[i - 1])
                            end = int(members[i + 1])
                            expanded_members.extend(range(start, end + 1))
                            i += 2
                        else:
                            expanded_members.append(int(members[i]))
                        i += 1
                    members = expanded_members
                else:
                    members = [int(member) for member in members]
                dimensions = tuple(map(float, property_data))
                for member in members:
                    member_properties[member] = dimensions

        current_line_index += 1

    return member_properties


def extract_joint_coordinates(lines):
    in_joint_coordinates = False
    joint_coordinates = {}

    for line in lines:
        stripped_line = line.strip()

        if "JOINT COORDINATES" in stripped_line:
            in_joint_coordinates = True
            continue

        if in_joint_coordinates:
            if "PAGE NO." in stripped_line:
                continue
            if stripped_line and not stripped_line.split(" ")[1].isdigit():
                break
            stripped_line = " ".join(stripped_line.split(" ")[1:])
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
    if len(dimensions) < 5:
        of = f"OF-"
        web = f"WEB-"
        if_ = f"IF-"
        return f"{of}\n{web}\n{if_}"
    
    if len(dimensions) == 5:
        dimensions = list(dimensions)
        dimensions.append(4)
        dimensions.append(5)

    if len(dimensions) == 6:
        dimensions = list(dimensions)
        dimensions.append(5)



    of = f"OF- {int(dimensions[3])}X{int(dimensions[4])}"
    web = f"WEB- {int(dimensions[1])}thk."
    if_ = f"IF- {int(dimensions[5])}X{int(dimensions[6])}"
    return f"{of}\n{web}\n{if_}"


def draw_frame(members_and_nodes, node_coordinates, member_dimension):
    fig, ax = plt.subplots(figsize=(12, 10))

    for member_no, dimensions in member_dimension.items():
        if dimensions:
            dimensions = list(dimensions)  # Convert tuple to list
            if len(dimensions) == 5:
                dimensions.append(4)
                dimensions.append(5)
            elif len(dimensions) == 6:
                dimensions.append(5)
            elif len(dimensions) < 5:
                while len(dimensions) < 7:
                    dimensions.append(1)
            member_dimension[member_no] = dimensions  # Update the dictionary with the modified list

    for member in members_and_nodes:
        member_no, bottom_joint, top_joint = member
        x1, y1, z1 = node_coordinates[bottom_joint]
        x2, y2, z2 = node_coordinates[top_joint]

        # Calculate the length of the member
        length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)

        x_values = [x1, x2]
        y_values = [y1, y2]
        # ax.plot(x_values, y_values, "o-", label=f"Member {member_no}")
        ax.plot(x_values, y_values, "o-", color="#a9a9a9", label=f"Member {member_no}")

        dimensions = member_dimension.get(int(member_no))
        if dimensions:
            dimension_label = format_dimension_label(dimensions)
            mid_x = (x_values[0] + x_values[1]) / 2
            mid_y = (y_values[0] + y_values[1]) / 2

            ax.text(
                mid_x,
                mid_y - 0.3,
                dimension_label,
                fontsize=8,
                color="yellow",
                ha="center",
                va="center",
                bbox=dict(
                    facecolor="black",
                    alpha=0.8,
                    edgecolor="none",
                    boxstyle="round,pad=0.1",
                ),
            )

            # Display the length above the member name
            ax.text(
                mid_x,
                mid_y + 0.1,
                f"{length:.3f}",
                fontsize=8,
                color="red",
                ha="center",
                va="center",
            )

            # Calculate and display values at bottom end

            bottom_end_value = dimensions[0] - dimensions[4] - dimensions[6]
            ax.text(
                x_values[0],
                y_values[0] + 0.14,
                f"{bottom_end_value}",
                fontsize=8,
                color="blue",
                ha="center",
                va="center",
            )

            # Calculate and display values at top end
            top_end_value = dimensions[2] - dimensions[4] - dimensions[6]
            ax.text(
                x_values[1],
                y_values[1] - 0.14,
                f"{top_end_value}",
                fontsize=8,
                color="blue",
                ha="center",
                va="center",
            )

    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title("Sections properties")
    ax.grid(False)
    ax.legend().set_visible(False)

    ax.set_xticks([])
    ax.set_yticks([])

    return fig, ax
