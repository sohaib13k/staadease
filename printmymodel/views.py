from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def get_frame_details(request):
    return render(request, "printmymodel/frame_details.html", {"result": ""})