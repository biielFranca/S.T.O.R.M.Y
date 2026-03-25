"""
Permite a Stormy gerenciar sua própria configuração e código.
Todas as alterações passam por confirmação do usuário antes de serem aplicadas.
"""

import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"

# Alterações pendentes aguardando confirmação
_pending: dict | None = None


def _read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    result = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env(data: dict[str, str]) -> None:
    lines = []
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=")[0].strip()
                if key in data:
                    lines.append(f"{key}={data.pop(key)}")
                else:
                    lines.append(line)
            else:
                lines.append(line)
    # Adiciona chaves novas que não existiam
    for key, val in data.items():
        lines.append(f"{key}={val}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def propose_api_key(key_name: str, key_value: str, description: str = "") -> str:
    """
    Propõe salvar uma chave de API no .env.
    Retorna mensagem pedindo confirmação ao usuário.
    """
    global _pending
    _pending = {
        "type": "env_key",
        "key_name": key_name,
        "key_value": key_value,
        "description": description,
    }
    desc = f" ({description})" if description else ""
    return (
        f"Vou salvar {key_name}={key_value[:8]}...{key_value[-4:]}{desc} no .env. "
        f"Confirma? (responde 'confirma' ou 'cancela')"
    )


def propose_code_change(file_name: str, description: str, old_code: str, new_code: str) -> str:
    """
    Propõe uma alteração em um arquivo de código.
    Retorna mensagem pedindo confirmação.
    """
    global _pending
    _pending = {
        "type": "code_change",
        "file_name": file_name,
        "description": description,
        "old_code": old_code,
        "new_code": new_code,
    }
    return (
        f"Vou fazer essa alteração em {file_name}:\n"
        f"{description}\n\n"
        f"Confirma? (responde 'confirma' ou 'cancela')"
    )


def confirm_pending() -> str:
    """Executa a alteração pendente."""
    global _pending
    if not _pending:
        return "Não tem nada pendente pra confirmar."

    action = _pending.copy()
    _pending = None

    if action["type"] == "env_key":
        try:
            env = _read_env()
            env[action["key_name"]] = action["key_value"]
            _write_env(env)
            # Recarrega variáveis de ambiente em tempo real
            os.environ[action["key_name"]] = action["key_value"]
            return f"Feito! {action['key_name']} salva no .env e ativada. Pode usar agora."
        except Exception as e:
            return f"Erro ao salvar: {e}"

    if action["type"] == "code_change":
        try:
            file_path = BASE_DIR / action["file_name"]
            if not file_path.exists():
                return f"Arquivo {action['file_name']} não encontrado."
            content = file_path.read_text(encoding="utf-8")
            if action["old_code"] not in content:
                return f"Não encontrei o trecho pra substituir em {action['file_name']}."
            new_content = content.replace(action["old_code"], action["new_code"], 1)
            file_path.write_text(new_content, encoding="utf-8")
            return f"Feito! {action['file_name']} atualizado. Reinicia a Stormy pra aplicar."
        except Exception as e:
            return f"Erro ao editar arquivo: {e}"

    return "Tipo de ação desconhecido."


def cancel_pending() -> str:
    """Cancela a alteração pendente."""
    global _pending
    if not _pending:
        return "Não tem nada pendente."
    _pending = None
    return "Cancelado, prc."


def has_pending() -> bool:
    return _pending is not None


def get_current_keys() -> str:
    """Lista as chaves configuradas no .env (sem mostrar os valores completos)."""
    env = _read_env()
    if not env:
        return "Nenhuma chave configurada ainda."
    lines = ["Chaves configuradas:"]
    for key, val in env.items():
        masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
        lines.append(f"  {key} = {masked}")
    return "\n".join(lines)
