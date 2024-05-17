# views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponse
import matplotlib.pyplot as plt
from io import BytesIO
from django.core.files.storage import FileSystemStorage
import base64

@login_required
def get_frame_details(request):
    if request.method == 'POST':
        anl_file = request.FILES.get('anl_file')
        if anl_file:
            fs = FileSystemStorage(location=settings.MODEL_DIR)
            filename = fs.save(anl_file.name, anl_file)
            file_path = fs.path(filename)
            
            with open(file_path, 'r') as file:
                lines = file.readlines()

            joined_frame = join_members(lines)
            member_dimension = extract_member_dimensions(lines)
            member_properties_multiplied = {}
            for member, dimensions in member_dimension.items():
                member_properties_multiplied[member] = tuple(int(dim * 1000) for dim in dimensions)
            node_coordinates = extract_joint_coordinates(lines)

            fig, ax = draw_frame(joined_frame, node_coordinates, member_properties_multiplied)

            # Save the figure to a BytesIO object as SVG
            buffer = BytesIO()
            fig.savefig(buffer, format='svg')
            buffer.seek(0)
            svg_data = buffer.getvalue().decode('utf-8')
            
            return render(request, 'printmymodel/file_upload_success.html', {'svg_data': svg_data})

    return render(request, 'printmymodel/frame_details.html')


def join_members(lines):
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

            if stripped_line and not stripped_line.split(' ')[1].isdigit():
                break
            stripped_line = ' '.join(stripped_line.split(' ')[1:])
            parts = stripped_line.split(';')
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

            if "*---------------------------------------------------------------------------*" in line:
                break
            
            if "TABLE" in stripped_line:
                current_line_index += 1
                continue

            if stripped_line.endswith('-'):
                combined_line = stripped_line[:-1].strip()
                next_line_index = current_line_index + 1
                while next_line_index < len(lines):
                    next_line = lines[next_line_index].strip()
                    if next_line.endswith('-'):
                        combined_line += ' ' + next_line[:-1].strip()
                        next_line_index += 1
                    elif "TABLE" in next_line:
                        current_line_index = next_line_index + 1
                        break
                    else:
                        combined_line += ' ' + next_line
                        current_line_index = next_line_index
                        break
                stripped_line = combined_line

            if "TABLE" in stripped_line:
                current_line_index += 1
                continue

            stripped_line = ' '.join(stripped_line.split(' ')[1:])
            parts = stripped_line.split(' ')
            property_data = []
            members = []
            dimensions_start = False
            for part in parts:
                if part.isdigit() or (part == 'TO'):
                    members.append(part)
                else:
                    if part != 'TAPERED':
                        dimensions_start = True
                        property_data.append(part)

            if dimensions_start:
                if 'TO' in members:
                    expanded_members = []
                    i = 0
                    while i < len(members):
                        if members[i] == 'TO':
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
            if stripped_line and not stripped_line.split(' ')[1].isdigit():
                break
            stripped_line = ' '.join(stripped_line.split(' ')[1:])
            parts = stripped_line.split(';')
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
    of = f"OF - {int(dimensions[3])}X{int(dimensions[4])}"
    web = f"WEB - {int(dimensions[1])}thk."
    if_ = f"IF - {int(dimensions[5])}X{int(dimensions[6])}"
    return f"{of}\n{web}\n{if_}"

def draw_frame(members_and_nodes, node_coordinates, member_dimension):
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_facecolor('black')
    
    for member in members_and_nodes:
        member_no, bottom_joint, top_joint = member
        x_values = [node_coordinates[bottom_joint][0], node_coordinates[top_joint][0]]
        y_values = [node_coordinates[bottom_joint][1], node_coordinates[top_joint][1]]
        ax.plot(x_values, y_values, 'yo-', label=f'Member {member_no}')  # Yellow lines

        dimensions = member_dimension.get(int(member_no))
        if dimensions:
            dimension_label = format_dimension_label(dimensions)
            mid_x = (x_values[0] + x_values[1]) / 2
            mid_y = (y_values[0] + y_values[1]) / 2
            ax.text(mid_x, mid_y + 0.4, member_no, fontsize=8, color='white', ha='center', va='center')  # Member number in white
            ax.text(mid_x, mid_y - 0.4, dimension_label, fontsize=8, color='white', ha='center', va='center')  # Dimension label in white

    for node, (x, y, z) in node_coordinates.items():
        ax.scatter(x, y, color='red')  # Red nodes

    ax.set_xlabel('X Coordinate', color='white')
    ax.set_ylabel('Y Coordinate', color='white')
    ax.set_title('Gate-like Structure', color='white')
    ax.grid(False)
    ax.legend().set_visible(False)

    return fig, ax
