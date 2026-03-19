# Gunakan image resmi Nginx
FROM nginx:latest

# Hapus konfigurasi default Nginx agar tidak bentrok
RUN rm /etc/nginx/conf.d/default.conf

# Copy file nginx.conf milikmu ke dalam folder konfigurasi Nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Expose port 80
EXPOSE 80