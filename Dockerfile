FROM continuumio/miniconda3:4.10.3
MAINTAINER Mingxun Wang "mwang87@gmail.com"

RUN apt-get update && apt-get install -y build-essential libarchive-dev wget vim

COPY requirements.txt .
RUN pip install -r requirements.txt

# Installing Nextflow
RUN conda install -c bioconda nextflow

# Installing mamba
RUN conda install -c conda-forge mamba

COPY . /app
WORKDIR /app
