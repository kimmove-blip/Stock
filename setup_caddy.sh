#!/bin/bash
# Caddy 설정 업데이트 스크립트

# 백업
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.backup

# 새 설정 적용
sudo tee /etc/caddy/Caddyfile > /dev/null << 'EOF'
code.kimhc.dedyn.io {
    reverse_proxy localhost:8080
}

n8n.kimhc.dedyn.io {
    request_body {
        max_size 100MB
    }

    header Access-Control-Allow-Origin *

    @options method OPTIONS
    handle @options {
        header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS"
        header Access-Control-Allow-Headers "Content-Type, Authorization"
        respond "" 204
    }

    handle /shorts/* {
        root * /home/kimhc/youtube_factory
        file_server browse
    }

    reverse_proxy localhost:5678 {
        transport http {
            read_timeout 300s
            write_timeout 300s
        }

        header_down -Access-Control-Allow-Origin
        header_down Access-Control-Allow-Origin *
    }
}

eml.kimhc.dedyn.io {
    reverse_proxy localhost:8502
}

trip.kimhc.dedyn.io {
    reverse_proxy localhost:5000
}

stock.kimhc.dedyn.io {
    handle /apple-touch-icon.png {
        root * /home/kimhc/Stock/static
        file_server
    }

    # FastAPI 백엔드 (모바일 앱용)
    handle /api/* {
        reverse_proxy localhost:8000
    }

    # Streamlit 웹 대시보드
    reverse_proxy localhost:8501
}

# PWA 앱 (별도 서브도메인)
app.kimhc.dedyn.io {
    # API 프록시
    handle /api/* {
        reverse_proxy localhost:8000
    }

    # PWA 정적 파일
    reverse_proxy localhost:3000
}
EOF

# Caddy 재시작
sudo systemctl reload caddy

echo "Caddy 설정 업데이트 완료"
echo "- 기존 웹: https://stock.kimhc.dedyn.io"
echo "- PWA 앱:  https://app.kimhc.dedyn.io"
echo "- API:     https://stock.kimhc.dedyn.io/api/*"
