# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /app
COPY ./app /app/app

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable
ENV MODULE_NAME="app.main"
ENV VARIABLE_NAME="app"
# ENV LOG_LEVEL="info" # You can set this via docker-compose or direct run

# Run app.main:app when the container launches
# Use uvicorn with --host 0.0.0.0 to allow external connections
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
