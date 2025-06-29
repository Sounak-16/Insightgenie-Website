import os
import json
import pandas as pd
import plotly
import plotly.express as px
import requests
from django.conf import settings
from django.http import FileResponse
from django.core.files.storage import FileSystemStorage
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib import messages

from .forms import UploadCSVForm

class SignUpView(CreateView):
    form_class = UserCreationForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('login')

class CustomLoginView(LoginView):
    template_name = 'users/login.html'

class CustomLogoutView(LogoutView):
    next_page = 'login'

def ask_csv_question(df, question):
    if df.empty:
        return "No data available to ask questions about. Please upload a file."

    sample = df.head(5).to_string(index=False)
    prompt = f"""You are a data analyst. Analyze the following CSV sample and answer the question.

CSV:
{sample}

Question:
{question}
"""

    try:
        response = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.TOGETHER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistralai/Mistral-7-Instruct-v0.2",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 256,
                "temperature": 0.7
            }
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return f"Sorry, I couldn't connect to the AI service. Error: {e}"
    except KeyError:
        print(f"Unexpected API response: {response.json()}")
        return "Sorry, I received an unexpected response from the AI service."

def extract_column_names(question, df_columns):
    matched = []
    question = question.lower()
    for col in df_columns:
        if col.lower() in question:
            matched.append(col)
    return matched

@login_required
def dashboard_view(request):
    df = pd.DataFrame()
    data_preview = None
    summary = None
    form = UploadCSVForm()
    plot_json = None
    column_options = []
    selected_x = None
    selected_y = None
    answer = None
    chart_type = 'histogram'

    file_path = request.session.get('uploaded_file_path')
    has_file = bool(file_path)
    if has_file and os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path) if file_path.endswith('.csv') else pd.read_excel(file_path)
        except Exception as e:
            messages.error(request, f"Error loading file: {e}")
            request.session.pop('uploaded_file_path', None)
            df = pd.DataFrame()
            has_file = False

    if request.method == 'POST':
        if 'file' in request.FILES:
            form = UploadCSVForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = form.cleaned_data['file']
                fs = FileSystemStorage()
                filename = fs.save(csv_file.name, csv_file)
                file_path = fs.path(filename)
                request.session['uploaded_file_path'] = file_path
                messages.success(request, "File uploaded successfully!")
                return redirect('dashboard')

        elif 'download_file' in request.POST:
            if file_path and os.path.exists(file_path):
                return FileResponse(open(file_path, 'rb'), as_attachment=True)

        elif 'delete_file' in request.POST:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                messages.success(request, "File deleted successfully.")
                request.session.pop('uploaded_file_path', None)
                return redirect('dashboard')

        elif 'update_chart' in request.POST and has_file:
            selected_x = request.POST.get('x_column')
            selected_y = request.POST.get('y_column')
            chart_type = request.POST.get('chart_type', 'histogram')

            try:
                if selected_x and selected_x in df.columns:
                    x_data = pd.to_numeric(df[selected_x], errors='coerce') if df[selected_x].dtype != 'object' else df[selected_x]

                    if selected_y and selected_y in df.columns:
                        y_data = pd.to_numeric(df[selected_y], errors='coerce') if df[selected_y].dtype != 'object' else df[selected_y]

                        if chart_type == 'scatter':
                            fig = px.scatter(df, x=selected_x, y=selected_y, title=f"{selected_y} vs {selected_x}")
                        elif chart_type == 'line':
                            fig = px.line(df, x=selected_x, y=selected_y, title=f"{selected_y} over {selected_x}")
                        elif chart_type == 'bar':
                            fig = px.bar(df, x=selected_x, y=selected_y, title=f"{selected_y} by {selected_x}")
                        else:
                            fig = px.histogram(df, x=selected_x, title=f"Histogram of {selected_x}")
                    else:
                        if chart_type == 'box':
                            fig = px.box(df, y=x_data, title=f"Box Plot of {selected_x}")
                        elif chart_type == 'line':
                            fig = px.line(df, y=x_data, title=f"Line Chart of {selected_x}")
                        elif chart_type == 'bar':
                            value_counts = df[selected_x].value_counts().nlargest(10)
                            fig = px.bar(x=value_counts.index, y=value_counts.values,
                                         title=f"Bar Chart of {selected_x}")
                        else:
                            fig = px.histogram(df, x=x_data, nbins=20, title=f"Histogram of {selected_x}")

                    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=400)
                    plot_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

            except Exception as e:
                messages.warning(request, f"Failed to generate chart: {e}")

    if not df.empty:
        data_preview = df.head().to_html(classes='table table-striped')
        summary = df.describe(include='all').to_html(classes='table table-bordered')
        column_options = df.columns.tolist()
        if not selected_x and column_options:
            selected_x = column_options[0]

    return render(request, 'users/dashboard.html', {
        'form': form,
        'data_preview': data_preview,
        'summary': summary,
        'plot_json': plot_json,
        'column_options': column_options,
        'selected_x': selected_x,
        'selected_y': selected_y,
        'has_file': has_file,
        'answer': answer,
        'chart_type': chart_type,
    })
