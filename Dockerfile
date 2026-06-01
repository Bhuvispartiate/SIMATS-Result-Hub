FROM python:3.11

# Set the working directory
WORKDIR /code

# Copy the requirements file into the container
COPY ./requirements.txt /code/requirements.txt

# Install the Python dependencies
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Create a non-root user (user ID 1000) as required by Hugging Face Spaces
RUN useradd -m -u 1000 user

# Switch to the new non-root user
USER user

# Define environment variables for the user path
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Change the working directory to the user's home
WORKDIR $HOME/app

# Copy the rest of the application files to the container with correct permissions
COPY --chown=user . $HOME/app

# Run the FastAPI application on port 7860 using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
