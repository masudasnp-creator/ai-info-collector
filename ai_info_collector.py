import feedparser
import requests
from datetime import datetime, timedelta
import json
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
import io

class AIInfoCollector:
    def __init__(self):
        self.sources = {
            'openai_blog': 'https://openai.com/blog/rss.xml',
            'anthropic_blog': 'https://www.anthropic.com/news/rss.xml',
            'google_ai_blog': 'https://blog.google/products/ai/rss/',
            'hugging_face': 'https://huggingface.co/blog/feed.xml',
            'github_trending': 'https://github.com/trending/python.atom',
            'papers_with_code': 'https://paperswithcode.com/feed.xml'
        }
        
        self.coding_keywords = [
            'coding', 'programming', 'github copilot', 'code generation',
            'software development', 'IDE', 'cursor IDE', 'replit',
            'code assistant', 'developer tools', 'API'
        ]
    
    def setup_google_drive(self):
        """Google Drive API setup"""
        from google.oauth2 import service_account
        
        # サービスアカウント認証情報を使用
        creds = service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        self.drive_service = build('drive', 'v3', credentials=creds)
        
    def fetch_rss_content(self, url):
        """RSS フィードから記事を取得"""
        try:
            feed = feedparser.parse(url)
            articles = []
            
            # 過去1週間の記事のみ
            week_ago = datetime.now() - timedelta(days=7)
            
            for entry in feed.entries:
                pub_date = datetime(*entry.published_parsed[:6])
                if pub_date > week_ago:
                    # コーディング関連キーワードでフィルタ
                    if self.is_coding_related(entry.title + " " + entry.summary):
                        articles.append({
                            'title': entry.title,
                            'link': entry.link,
                            'summary': entry.summary,
                            'published': pub_date.strftime('%Y-%m-%d'),
                            'source': url
                        })
            return articles
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return []
    
    def is_coding_related(self, text):
        """コーディング関連かチェック"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.coding_keywords)
    
    def fetch_github_trending(self):
        """GitHub Trending AI repositories"""
        try:
            url = "https://api.github.com/search/repositories"
            params = {
                'q': 'ai OR machine-learning OR llm created:>2024-05-25',
                'sort': 'stars',
                'order': 'desc',
                'per_page': 20
            }
            
            response = requests.get(url, params=params)
            repos = response.json()['items']
            
            trending_repos = []
            for repo in repos:
                trending_repos.append({
                    'name': repo['name'],
                    'description': repo['description'],
                    'url': repo['html_url'],
                    'stars': repo['stargazers_count'],
                    'language': repo['language']
                })
            
            return trending_repos
        except Exception as e:
            print(f"Error fetching GitHub trending: {e}")
            return []
    
    def collect_all_info(self):
        """全ての情報を収集"""
        collected_data = {
            'generated_at': datetime.now().isoformat(),
            'articles': [],
            'github_repos': []
        }
        
        # RSS記事収集
        for source_name, url in self.sources.items():
            print(f"Collecting from {source_name}...")
            articles = self.fetch_rss_content(url)
            for article in articles:
                article['source_name'] = source_name
            collected_data['articles'].extend(articles)
        
        # GitHub trending収集
        print("Collecting GitHub trending...")
        collected_data['github_repos'] = self.fetch_github_trending()
        
        return collected_data
    
    def create_summary_document(self, data):
        """収集した情報をドキュメント形式に整理"""
        doc_content = f"""# AI開発情報 週次レポート
生成日時: {data['generated_at']}

## 最新記事・ニュース ({len(data['articles'])}件)

"""
        
        # 記事をソース別に整理
        sources = {}
        for article in data['articles']:
            source = article['source_name']
            if source not in sources:
                sources[source] = []
            sources[source].append(article)
        
        for source_name, articles in sources.items():
            doc_content += f"### {source_name.replace('_', ' ').title()}\n\n"
            for article in articles:
                doc_content += f"**{article['title']}**\n"
                doc_content += f"- 公開日: {article['published']}\n"
                doc_content += f"- URL: {article['link']}\n"
                doc_content += f"- 概要: {article['summary'][:200]}...\n\n"
        
        # GitHub trending repos
        doc_content += f"\n## GitHub トレンドリポジトリ ({len(data['github_repos'])}件)\n\n"
        for repo in data['github_repos']:
            doc_content += f"**{repo['name']}** ({repo['language']}) - ⭐{repo['stars']}\n"
            doc_content += f"- {repo['description']}\n"
            doc_content += f"- {repo['url']}\n\n"
        
        return doc_content
    
    def upload_to_drive(self, content, filename):
        """Google Driveにアップロード"""
        try:
            file_metadata = {
                'name': filename,
                'parents': [os.getenv('DRIVE_FOLDER_ID')]  # 環境変数で指定
            }
            
            media = MediaIoBaseUpload(
                io.BytesIO(content.encode('utf-8')),
                mimetype='text/plain'
            )
            
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            print(f'File uploaded: {file.get("id")}')
            return file.get('id')
        
        except Exception as e:
            print(f'Error uploading to Drive: {e}')
            return None
    
    def run_weekly_collection(self):
        """週次実行メイン処理"""
        print("Starting weekly AI info collection...")
        
        # Google Drive setup
        self.setup_google_drive()
        
        # データ収集
        data = self.collect_all_info()
        
        # ドキュメント作成
        document = self.create_summary_document(data)
        
        # ファイル名生成
        filename = f"AI_Weekly_Report_{datetime.now().strftime('%Y%m%d')}.txt"
        
        # Google Driveにアップロード
        file_id = self.upload_to_drive(document, filename)
        
        if file_id:
            print(f"Weekly report successfully uploaded: {filename}")
            print("Manual step: Import this file to NotebookLM")
        
        return data

if __name__ == "__main__":
    collector = AIInfoCollector()
    collector.run_weekly_collection()
