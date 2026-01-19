#!/bin/bash

# ######################################################################################
# Small script to setup and build picoquic-multicast on Debian/Ubuntu and get demo files
# ######################################################################################

# Install packages
apt update && apt install -y \
    cmake \
    make \
    autoconf \
    libtool-bin \
    build-essential \
    libssl-dev \
    openssl \
    pkg-config \
    unzip \
    sysstat \
    tshark \
    time \
    ntp \
    cpufrequtils

mkdir multicast && cd multicast

# Install and build libmcrx
git clone https://github.com/GrumpyOldTroll/libmcrx
cd libmcrx && ./autogen.sh && ./configure && make && make install && cd ..

# Install and build picoquic-multicast with picotls
git clone https://github.com/j0nem/picoquic-multicast
cmake -S picoquic-multicast/ -B build/ -DPICOQUIC_FETCH_PTLS=Y
cd build && make multicast dgramspl && cd ..
mkdir application && cd application

# Generate certificates
mkdir -p server/files && mkdir client
openssl req -batch -noenc -x509 -newkey rsa:2048 -days 365 -keyout server/ca-key.pem -out server/ca-cert.pem
openssl req -batch -noenc -newkey rsa:2048 -keyout server/server-key.pem -out server/server-req.pem

# Download sample server data
curl https://download.blender.org/demo/movies/BBB/bbb_sunflower_1080p_30fps_normal.mp4.zip > server/files/bbb.zip
unzip server/files/bbb.zip -d server/files/
rm server/files/bbb.zip
mv server/files/bbb_sunflower_1080p_30fps_normal.mp4 server/files/bbb.mp4

# Start data collection
systemctl enable sysstat
systemctl enable ntp
systemctl start sysstat
systemctl start ntp

cpufreq-set -g performance