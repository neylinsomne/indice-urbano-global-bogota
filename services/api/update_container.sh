#!/bin/bash


docker build -t img_fasta .


docker stop container_fasta


docker rm container_fasta


docker run -d -p 80:80 --name container_fasta img_fasta

echo "Container 'container_fasta' has been updated and is running with the new image 'img_fasta'."

#chmod +x update_container.sh -> se hace un ejecutable y se debe correr en gitbash
