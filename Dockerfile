FROM ubuntu:22.04
MAINTAINER Mingxun Wang "mwang87@gmail.com"

RUN apt-get update && apt-get install -y build-essential libarchive-dev wget vim unzip

# Install Mamba
ENV CONDA_DIR /opt/conda
RUN wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -O ~/miniforge.sh && /bin/bash ~/miniforge.sh -b -p /opt/conda
ENV PATH=$CONDA_DIR/bin:$PATH

# Adding to bashrc
RUN echo "export PATH=$CONDA_DIR:$PATH" >> ~/.bashrc

# Forcing version of Python
RUN mamba create -n python310 python=3.10 -y

COPY requirements.txt .
RUN /bin/bash -c 'source activate python310 && pip install -r requirements.txt'

# Installing Nextflow
RUN mamba install -n python310 -c bioconda nextflow==24.04.4 -y

COPY . /app
WORKDIR /app
