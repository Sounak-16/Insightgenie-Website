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

# === Signup View ===
class SignUpView(CreateView):
    form_class = UserCreationForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('login')


# === Custom Login View ===
class CustomLoginView(LoginView):
    template_name = 'users/login.html'


# === Custom Logout View ===
class CustomLogoutView(LogoutView):
    next_page = 'login'


# === Ask AI Chatbot Function ===
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


# === Dashboard View ===
@login_required
def dashboard_view(request):
    df = pd.DataFrame()
    data_preview = None
    summary = None
    form = UploadCSVForm()
    plot_json = None
    column_options = []
    selected_column = None
    answer = None
    matched_columns = []

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
            else:
                messages.error(request, "Error uploading file.")

        file_path = request.session.get('uploaded_file_path')
        has_file = bool(file_path)

        if file_path and os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path) if file_path.endswith('.csv') else pd.read_excel(file_path)
            except Exception as e:
                messages.error(request, f"Error loading file: {e}")
                request.session.pop('uploaded_file_path', None)
                df = pd.DataFrame()
                has_file = False

        if 'ask' in request.POST and has_file:
            question = request.POST.get('question')
            matched_columns = extract_column_names(question, df.columns)
            if len(matched_columns) == 0:
                answer = "❌ Sorry, I couldn't identify any matching column names in your question."
            elif len(matched_columns) == 1:
                x = matched_columns[0]
                fig = px.histogram(df, x=x, title=f"Histogram of {x}")
                plot_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
                answer = f"🧠 Here's a histogram of {x}."
            elif len(matched_columns) == 2:
                x, y = matched_columns[:2]
                fig = px.scatter(df, x=x, y=y, title=f"{y} vs {x}")
                plot_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
                answer = f"🧠 Here's a scatter plot of {y} vs {x}."
            elif len(matched_columns) >= 3:
                x, y, z = matched_columns[:3]
                fig = px.scatter_3d(df, x=x, y=y, z=z, title=f"3D Plot of {x}, {y}, {z}")
                plot_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
                answer = f"🧠 Here's a 3D scatter plot for {x}, {y}, and {z}."

        elif 'delete_file' in request.POST:
            file_path = request.session.get('uploaded_file_path')
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                messages.success(request, "File deleted successfully.")
            request.session.pop('uploaded_file_path', None)
            return redirect('dashboard')

        elif 'download_file' in request.POST:
            file_path = request.session.get('uploaded_file_path')
            if file_path and os.path.exists(file_path):
                return FileResponse(open(file_path, 'rb'), as_attachment=True)
            else:
                messages.error(request, "No file to download.")
                return redirect('dashboard')

        elif 'column' in request.POST:
            selected_column = request.POST.get('column')

    else:
        file_path = request.session.get('uploaded_file_path')
        has_file = bool(file_path)
        if file_path and os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path) if file_path.endswith('.csv') else pd.read_excel(file_path)
            except Exception as e:
                messages.error(request, f"Failed to load file: {e}")
                request.session.pop('uploaded_file_path', None)
                df = pd.DataFrame()
                has_file = False

    if not df.empty:
        data_preview = df.head().to_html(classes='table table-striped')
        summary = df.describe(include='all').to_html(classes='table table-bordered')
        numeric_cols = df.select_dtypes(include='number').columns.tolist()
        column_options = numeric_cols
        if not selected_column and numeric_cols:
            selected_column = numeric_cols[0]

        if selected_column and selected_column in df.columns:
            try:
                cleaned_series = pd.to_numeric(df[selected_column], errors='coerce').dropna()
                if not cleaned_series.empty:
                    fig = px.histogram(cleaned_series, x=cleaned_series, nbins=20,
                                       title=f"Distribution of {selected_column}")
                    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=400)
                    plot_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
                else:
                    plot_json = None
                    messages.warning(request, f"No numeric data found in '{selected_column}' to plot.")
            except Exception as e:
                print(f"Error generating plot for {selected_column}: {e}")
                plot_json = None
                messages.warning(request, f"Could not generate plot for '{selected_column}'. Error: {e}")
    else:
        data_preview = "<p>No data uploaded yet.</p>"
        summary = "<p>Upload a CSV or Excel file to see its summary.</p>"

    return render(request, 'users/dashboard.html', {
        'form': form,
        'data_preview': data_preview,
        'summary': summary,
        'plot_json': plot_json,
        'column_options': column_options,
        'selected_column': selected_column,
        'has_file': has_file,
        'answer': answer,
    })
