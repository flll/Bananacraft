import json
import os
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from ai.key_store import apply_context
from ai.routing import AIStage, Provider, effective_route, image_model, resolve_api_key_for_stage, text_model
from ai.providers.stage_client import (
    anthropic_chat_json_turn,
    complete_json,
    complete_text,
    gemini_chat_json_turn,
    generate_image_bytes,
)

# 外部参照用（ルーティングの有効モデル）
TEXT_MODEL = text_model(AIStage.CONCEPT_BRAIN)
CHAT_MODEL = TEXT_MODEL
IMAGE_MODEL = image_model(AIStage.IMAGE_RENDER)


class GeminiClient:
    """
    コンセプト〜区画〜画像のクライアント。
    コンセプト対話は routing に従い Anthropic / Google を切替。
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        api_key が渡された場合は GEMINI_API_KEY としてランタイムにも反映（従来互換）。
        """
        self._override = api_key
        if api_key:
            apply_context({"GEMINI_API_KEY": api_key})
        self.chat_session = None
        self._concept_history: List[Dict[str, Any]] = []
        self.system_instruction = """
        あなたは世界最高峰のMinecraftコンセプトアーティストであり、プロンプトエンジニアです。
        ユーザーから提供される「曖昧なテーマ」は、200x200ブロックの広大な「街」や「都市」の建設予定地のためのものです。
        単体の建物ではなく、街全体の雰囲気、区画、複数の建物の配置、道路、地形が見渡せるような「鳥瞰図（Bird's-eye view）」や「広角ショット」のコンセプトアートを描くためのプロンプトを作成してください。

        【重要】生成された画像は後続の3Dモデル化処理に使用されます。以下の点を必ずプロンプトに含めてください：
        - ボクセル/キューブ状のブロックが明確に分かる表現
        - 鮮やかで識別しやすい配色（後のブロック変換で色が失われないようにするため）
        - Minecraft Bedrock Editionに実在するブロックを意識したテクスチャ

        以下のJSON形式で常に出力してください：
        {
            "reasoning": "なぜそのようなプロンプトにしたのか、どのような情景（街の規模感、広がり）を想像したのかの日本語による思考プロセス・解説",
            "image_prompt": "画像生成AI（Nano Banana Pro）に入力するための詳細な日本語プロンプト。必ず『広大な街の全景』『鳥瞰図』『200x200ブロックの規模感』『複数の建物』『道』『地形』といった要素を含め、単体の建物アップにならないようにしてください。光の表現、建築様式、ボクセル/キューブ表現、色彩設計、環境（天候、時間帯）、質感も具体的に含めてください。"
        }
        """

    def start_chat(self, history=None):
        route = effective_route(AIStage.CONCEPT_BRAIN)
        key = resolve_api_key_for_stage(AIStage.CONCEPT_BRAIN)
        if route.provider == Provider.GOOGLE:
            client = genai.Client(api_key=key)
            config = types.GenerateContentConfig(
                system_instruction=self.system_instruction,
                response_mime_type="application/json",
            )
            self.chat_session = client.chats.create(
                model=text_model(AIStage.CONCEPT_BRAIN),
                config=config,
                history=history or [],
            )
        else:
            self.chat_session = None
            self._concept_history = list(history or [])
        return self.chat_session

    def refine_prompt(self, user_input: str):
        route = effective_route(AIStage.CONCEPT_BRAIN)
        key = resolve_api_key_for_stage(AIStage.CONCEPT_BRAIN)
        print(f"Concept refine ({route.provider.name}): {user_input[:80]}...")
        if route.provider == Provider.GOOGLE:
            if not self.chat_session:
                self.start_chat()
            assert self.chat_session is not None
            return gemini_chat_json_turn(chat_session=self.chat_session, user_message=user_input)

        parsed, self._concept_history = anthropic_chat_json_turn(
            system=self.system_instruction.strip(),
            user_message=user_input,
            history=self._concept_history,
            model=text_model(AIStage.CONCEPT_BRAIN),
            api_key=key,
        )
        return parsed

    def generate_text(self, prompt: str, system_instruction: str = None, image_bytes: bytes = None) -> str:
        sys = system_instruction or "You are a helpful assistant."
        return complete_text(
            AIStage.CONCEPT_BRAIN,
            system=sys,
            user=prompt,
            temperature=0.4,
            image_bytes=image_bytes,
            image_mime="image/jpeg",
        )

    def generate_image(self, prompt: str, reference_image_bytes: bytes = None):
        try:
            print(f"Generating image with prompt: {prompt[:50]}...")
            return generate_image_bytes(
                prompt=prompt, reference_image_bytes=reference_image_bytes, reference_mime="image/jpeg"
            )
        except Exception as e:
            print(f"Image generation error: {e}")
            return None

    def generate_concept_image(
        self, base_description: str, width: int, depth: int, concept_image_bytes: bytes = None
    ):
        prompt = (
            f"マインクラフト（Minecraft）のボクセル建築物の画像を生成してください。\n"
            f"\n"
            f"【建築物の説明】\n"
            f"{base_description}\n"
            f"\n"
            f"【建築サイズ】幅 {width} ブロック × 奥行 {depth} ブロック\n"
            f"\n"
            f"【視点・構図】※3Dモデル化のため非常に重要\n"
            f"- 斜め上45度からのアイソメトリック視点（Isometric view）\n"
            f"- 建物全体が画面内に収まること（上下左右に適度な余白）\n"
            f"- 建物は画面の中央に配置\n"
            f"\n"
            f"【背景】\n"
            f"- シンプルな空のグラデーション背景のみ（他の建物や地形は配置しない）\n"
            f"- 建物の輪郭が背景から明確に分離できること\n"
            f"\n"
            f"【スタイル・テクスチャ】\n"
            f"- Minecraft Bedrock Edition (Vanilla) に実在するブロックのテクスチャを使用\n"
            f"- 1ブロック = 1立方体が明確に分かるボクセルスタイル\n"
            f"- 鮮やかで識別しやすい配色（パステルや淡い色は避ける）\n"
            f"\n"
            f"【ライティング】\n"
            f"- 柔らかい自然光（影MOD風でもOK）\n"
            f"- ブロックの色が正確に分かる明るさ\n"
            f"\n"
            f"【装飾】\n"
            f"- 理想的な完成形として装飾を含めてOK\n"
            f"- ランタン、旗、植物、フェンスなどで雰囲気を演出\n"
            f"\n"
            f"【参照画像について】\n"
            f"添付のコンセプトアート（街の全景）の世界観・配色・雰囲気を継承してください。"
        )
        print(f"--- Generating Decorated Image (Concept) ---\nPrompt: {prompt[:200]}...")
        return self.generate_image(prompt, reference_image_bytes=concept_image_bytes)

    def generate_structure_image(self, decorated_image_bytes: bytes):
        if not decorated_image_bytes:
            return None
        prompt = (
            "この建築画像を「3Dモデル生成用の躯体画像」に変換してください。\n"
            "\n"
            "【最重要ルール】絶対に守ってください\n"
            "1. **色を絶対に変えない**\n"
            "2. **形状を維持する**\n"
            "【削除するもの】細かい装飾のみ\n"
            "【残すもの】主要構造\n"
            "【出力スタイル】\n"
            "- 背景：純白 (#FFFFFF) の単色\n"
        )
        print(f"--- Generating Structure Image ---\nPrompt: {prompt[:200]}...")
        return self.generate_image(prompt, reference_image_bytes=decorated_image_bytes)

    def generate_zoning_json(self, concept_context: str):
        body = """
        あなたは熟練した都市計画家であり、マインクラフトの建築家です。
        以下の「確立したコンセプト」の世界観に基づき、200x200ブロックのエリアに建設する「街の設計図」を作成してください。

        【制約条件】
        エリア定義: ワールド座標 (x: 0, z: 0) を始点とし、(x: 200, z: 200) を終点とする正方形の範囲内です。
        創造的補完: 文脈から「この世界観なら当然あるべき施設（例：画像にお城があれば、城下町や兵舎など）」を想像して追加してください。
        配置ルール:
        - 【超重要】1つの区画（アイテム）には、必ず「単一の建築物」のみを配置すること。「高層ビル群」「住宅街」のように複数の建物を1つの区画にまとめることは禁止です。
        
        【建物サイズと数】
        巨大すぎる建築は品質が低下するため、以下のサイズ感で構成してください：
        - 中型建築（主要施設・役所・広場など）: 3〜5個 (幅・奥行き 20〜30ブロック程度)
        - 小型建築（一般住宅・商店・小屋など）: 15〜25個 (幅・奥行き 10〜15ブロック程度)
        ※「Landmark（超大型）」や「Large（大型）」は使用禁止です。複数の小型・中型建築で街を構成してください。

        【方角（Facing）と配置間隔】
        - **原則として「南向き（south）」**（Z軸プラス方向が正面）としてください。
        - **南側のスペース確保（必須）**: 各建物の南側（正面）には、**必ず10ブロック以上の何もないスペース**（庭、道路、広場用）を空けて配置してください。
        - もし南側10ブロック以内に他の建物がどうしても重なる配置になる場合のみ、道路や広場がある「空いている方向」を正面（facing）に指定してください。
        - 建物同士が絶対に重ならないように分散配置してください。

        【出力形式】 以下のJSON形式のみを出力してください。
        {
          "theme": "コンセプトテーマ",
          "area": {"start": [0, 0], "end": [200, 200]},
          "buildings": [
            {
              "id": 1,
              "name": "建物の名前",
              "type": "medium",
              "description": "外見や役割の詳細。",
              "position": {
                "x": 0,
                "z": 0,
                "width": 10,
                "depth": 10
              },
              "decorations": ["特徴的な装飾ブロックのアイデア"],
              "facing": "south"
            }
          ]
        }
        """
        header = ""
        if concept_context and concept_context.strip():
            header = "# 確立したコンセプト（デザインセッションより）\n" + concept_context.strip() + "\n\n"
        user_prompt = header + body
        text = complete_json(
            AIStage.ZONING_PLAN,
            system="You must output only valid JSON for the city layout.",
            user=user_prompt,
            temperature=0.3,
        )
        print(f"Zoning Raw Response: {text[:500]}...")
        try:
            return json.loads(text)
        except Exception:
            cleaned = text.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned)

    def generate_voxel_prompt(self, building_type: str, style: str = "Minecraft") -> str:
        print(f"Generating Voxel Prompt for: {building_type}...")
        system_instruction = """
        You are an expert 3D generative artist specializing in voxel art and Minecraft aesthetics.
        Your task is to create a highly detailed text prompt for an AI 3D model generator (Meshy).
        The goal is to generate a 3D model that looks like it belongs in Minecraft.
        Guidelines:
        1. Start with "Minecraft-style voxel [Object Name]".
        2. Emphasize "blocky geometric shapes", "cube-based architecture", "flat surfaces", "sharp edges".
        3. Explicitly forbid "organic curves", "round shapes", "high poly".
        4. Focus on architectural details: roof type, window style, materials (brick, stone, wood).
        5. Use keywords like "isometric game-ready asset", "low poly", "finely detailed textures".
        6. Keep the description under 500 characters.
        7. Output ONLY the English prompt.
        """
        user_prompt = f"Create a Meshy Text-to-3D prompt for a {style} style {building_type}."
        try:
            return self.generate_text(user_prompt, system_instruction=system_instruction)
        except Exception as e:
            print(f"Error generating voxel prompt: {e}")
            return f"Minecraft-style voxel {building_type}, blocky, low-poly, game asset"
