# GitHub 操作（gh CLI）

GitHub の認証情報は **`secret.env` / GSM `cursor-secret` に含めない**。各マシンで `gh auth login` する。

## 初回

```bash
gh auth login
# GitHub.com → HTTPS → Login with browser（または token は gh 設定のみに保存）
gh auth status
```

`gh` は git の credential helper になるため、`git push` / `git pull` も HTTPS で通る。

## よく使う操作

| 目的 | コマンド |
|------|----------|
| リポジトリ確認 | `gh repo view flll/Bananacraft` |
| PR 作成 | `gh pr create` |
| PR 一覧 | `gh pr list` |
| Skills 同期 | `make skills-sync`（`flll/skills` を clone/pull） |

## Skills リポジトリ（private）

```bash
make skills-sync
# または
git clone https://github.com/flll/skills.git ~/.cursor/skills-repo
~/.cursor/skills-repo/scripts/link-skills.sh
```

## 禁止

- `GITHUB_TOKEN` を `secret.env`・GSM・git に保存しない
- PAT を Cursor Rules やチャットに貼らない

Agent / CI で `gh` が必要なときは、その環境で一度 `gh auth login` する（または CI 用の `GH_TOKEN` を **CI のみ** に設定し、GSM には載せない）。
