# みおちゃんに聞かせて！理想の上司 — Oracle AI ブースデモ

[デモ仕様書](DEMO_SPEC.md)を実装した、独立起動型のブースデモです。既存環境が使用している`16385`には触れず、既定では`4317`を使用します。

## できること

- Select AI＋Gemini 2.5 Flashを使った、サーバ時刻基準60秒のレスキューゲーム
- MIO-RSによるターン採点、困り度・コンボ・コイン・ランク・称号の判定
- レスキュー結果の全期間TOP5ランキングと管理画面でのターン詳細確認
- `DBMS_VECTOR_CHAIN.UTL_TO_EMBEDDING`によるDB内ベクトル生成
- OCI Generative AI Chicagoの`cohere.embed-v4.0`（1536次元）を使用
- Oracle Databaseの`VECTOR(1536, FLOAT32)`型への保存
- `VECTOR_DISTANCE(..., COSINE)`を使った近い参加者の検索
- `python-oracledb`の常駐コネクションプールによる軽量なADB接続
- 価値観タイプ診断とリアルタイム会場スクリーン
- みおちゃんGIFの状態別切り替え
- ADBやOCI Generative AIが利用できない場合の安全なデモフォールバック

来場者フローは「エントリー → 理想の上司アンケート＋ゲーム説明 → 3・2・1 → 60秒レスキュー → スコア結果 → 価値観マッチ結果」です。レスキュー回答は採点とランキングにだけ使い、匿名の会場マップには理想の上司の回答だけを使います。旧業務QAの`/api/chat`は互換用に残しています。

`/why-oracle`では、Select AI、DB内Embedding、AI Vector Search、MDSによる3D会場マップ、API GatewayとADBプライベート・エンドポイントまで、デモを支える実装をライブ稼働情報とともに紹介します。

## 起動

### 1. GIFアセット

正式な9種類のGIFは`assets/miochan/`へ組み込み済みです。別バージョンへ差し替える場合は、次のインポートコマンドを使います。

```bash
./scripts/import_mio_assets.sh /Users/shunsukeniwa/Projects/codex/output/hatch-pet/mio/qa/previews
```

Linux環境では、同じ9ファイルがあるディレクトリを第1引数へ指定してください。ファイルが欠けている場合だけCSSアニメーションへフォールバックします。

### 2. まずメモリモードで起動する

```bash
./run.sh
```

- 来場者画面: `http://localhost:4317/`
- 大型会場画面: `http://localhost:4317/display`
- ヘルスチェック: `http://localhost:4317/api/health`
- API仕様: `http://localhost:4317/api/docs`

### 公開URL（ドメイン不要・HTTP）

- 来場者画面: `http://<PUBLIC_IP>/mio/`
- 大型会場画面: `http://<PUBLIC_IP>/mio/display`
- 参加者管理画面: `http://<PUBLIC_IP>/mio/admin`（既存画面にはリンク非掲載）

NginxはパブリックIPの`/mio/`だけを`127.0.0.1:4317`へ転送します。既存ホストのルートアプリは変更しません。設定例は`deploy/nginx/miochan.example.conf`です。

### 3. ADBを使う

秘密情報をコミットしないよう、`.env.example`を元にローカルの`.env`を作成します。

```bash
cp .env.example .env
```

`.env`の`MIO_ADB_PASSWORD`を設定し、初回だけ専用テーブルを作成します。

```bash
./scripts/init_adb.py
MIO_DATA_MODE=adb ./run.sh
```

従来の初期化に加え、レスキュー用テーブルと理想回答を非破壊で追加します。

```bash
./scripts/migrate_rescue.py
```

追加対象は`MIO_PLAYERS`、`MIO_GAME_SESSIONS`、`MIO_TURNS`、`MIO_IDEAL_ANSWERS`、`MIO_SCORE_EVENTS`、`MIO_ANSWER_TEMPLATES`です。既存のアンケート回答テーブルや会場マップのデータ構造は変更しません。
実行時のADB接続には`python-oracledb` ThickモードとSSO Walletを使用します。SQLclやJVMの子プロセスは起動しません。接続は最大4本のプールで再利用されます。

読み取り接続だけを確認する場合は次を実行します。

```bash
./scripts/check_adb.py
```

### 4. DB内Embeddingを構成する

Embeddingはアプリからベクトルを投入せず、回答テキストだけをADBへ渡します。ADBが`DBMS_VECTOR_CHAIN.UTL_TO_EMBEDDING`からOCI Generative AIのChicagoエンドポイントを呼び、`cohere.embed-v4.0`の1536次元ベクトルをDB内で生成・保存します。

初回のみ、OCI署名情報を標準入力から`configure_db_embedding.py`へ渡し、ADB内の資格証明`MIO_OCI_GENAI_CRED`とネットワークACLを構成します。秘密鍵はワークスペースやsystemd環境ファイルには保存しません。その後、既存回答を新しいベクトル列へ移行します。

```bash
./scripts/configure_db_embedding.py
./scripts/migrate_db_embeddings_v4.py
```

旧`answer_vector`列は切り戻し用に保持し、実行中の保存・類似検索・会場マップ・管理画面は`answer_vector_v4`だけを参照します。チャット応答用のOCI Generative AI設定はEmbeddingとは独立しています。

### 5. Select AI（Gemini 2.5 Flash）を構成する

既存のADB資格証明`MIO_OCI_GENAI_CRED`を使い、Chicagoリージョンの`google.gemini-2.5-flash`を会話対応プロファイル`MIO_GEMINI_FLASH`として作成します。`MIO_OCI_COMPARTMENT_OCID`を環境変数へ設定してから実行してください。

```bash
./scripts/configure_select_ai.py
```

カウントダウン後に待ち時間なく開始できるよう、初期発話とゲーム中の次の問いは安全な固定発話を即時返します。Gemini品質評価は会話履歴へ混ぜないステートレスな一括呼び出しとして結果確定時に実行します。Select AIまたはEmbeddingが一時的に失敗しても、固定発話と規則ベース採点へフォールバックしてゲームを完了できます。

ターン送信時は自然言語回答を先にADBへ保存して即座に次の問いを返します。Web APIプロセスではEmbeddingやSelect AIを実行しません。各Webサーバに置いた専用採点サービスが、空き時間に`UTL_TO_EMBEDDING`による1536次元化を進めます。

タイムアップまたは早期クリア時の`POST /finish`は、ADBのゲーム状態を`scoring`へ更新して`202 Accepted`を即時返却します。Web1・Web2の専用採点サービスが`FOR UPDATE SKIP LOCKED`でキューを共有し、二重処理を防ぎながら未処理Embedding、Geminiによる全ターン一括品質評価、MIO-RSの順序再計算を実行します。画面は採点中GIFを表示して結果APIをポーリングし、完成後に結果画面へ切り替わります。

理想の上司アンケートへ切り替える環境では、デモ用6名の回答とベクトルを次で更新します。

```bash
./scripts/migrate_supervisor_survey.py
```

## レスキューAPI

- `POST /api/mio/sessions` — 同意付きエントリーと60秒ゲーム開始
- `GET /api/mio/sessions/{session_id}` — リロード時の状態復元
- `POST /api/mio/sessions/{session_id}/turns` — 冪等なターン回答・採点
- `POST /api/mio/sessions/{session_id}/finish` — タイムアップを即時受付（採点中は202）
- `GET /api/mio/sessions/{session_id}/result` — 最終スコア・ランク・称号
- `GET /api/mio/venue/scoreboard` — 全期間最高スコア、最新完了者、TOP5

既存の`/api/survey`、`/api/network`、管理API、`/api/chat`も継続して利用できます。

## 検証

```bash
python3 -m unittest discover -s tests -v
```

## ポート変更

```bash
MIO_PORT=4318 ./run.sh
```

`MIO_PORT`以外の既存プロセスや設定は変更しません。

## 恒久サービス運用

公開環境では`mio-demo.service`としてsystemdへ登録し、Nginxから`127.0.0.1:4317`へ接続します。ADB認証情報はプロジェクト外の`/etc/mio-demo.env`へroot専用権限600で保存します。

Web APIとは別に`miochan-scoring.service`を各Webサーバで起動します。標準設定は1台あたり2並列、Web1・Web2合計4並列です。両サービスは同じADBキューを安全に共有します。

```bash
sudo systemctl status mio-demo.service
sudo systemctl restart mio-demo.service
sudo journalctl -u mio-demo.service -f
sudo systemctl status miochan-scoring.service
sudo journalctl -u miochan-scoring.service -f
```

サービス定義の配布元は`deploy/mio-demo.service`です。OS起動時に自動起動し、プロセス障害時は3秒後に自動再起動します。
