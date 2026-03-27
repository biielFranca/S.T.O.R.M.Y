const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const express = require("express");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");

// ── Config ──────────────────────────────────────────────────────────────────

const PORT = 3001;
const STORMY_URL = "http://localhost:5000/whatsapp/incoming";
const MEDIA_DIR = path.join(__dirname, "media");
const AUTH_DIR = path.join(__dirname, "wwebjs_auth");

if (!fs.existsSync(MEDIA_DIR)) fs.mkdirSync(MEDIA_DIR, { recursive: true });

// ── WhatsApp Client ─────────────────────────────────────────────────────────

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: AUTH_DIR }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
  restartOnAuthFail: true,
});

let clientReady = false;
let authenticatedNumber = null;

client.on("qr", (qr) => {
  console.log("[WhatsApp] Escaneie o QR code abaixo:");
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => {
  console.log("[WhatsApp] Autenticado com sucesso.");
});

client.on("auth_failure", (msg) => {
  console.error("[WhatsApp] Falha na autenticação:", msg);
});

client.on("ready", async () => {
  clientReady = true;
  const info = client.info;
  authenticatedNumber = info?.wid?.user || null;
  console.log(`[WhatsApp] Conectado como ${authenticatedNumber}`);
});

client.on("disconnected", (reason) => {
  console.log("[WhatsApp] Desconectado:", reason);
  clientReady = false;
  authenticatedNumber = null;
  console.log("[WhatsApp] Reconectando em 5s...");
  setTimeout(() => client.initialize(), 5000);
});

// ── Recebimento de mensagens ────────────────────────────────────────────────

client.on("message", async (msg) => {
  try {
    const chat = await msg.getChat();
    const contact = await msg.getContact();

    // Determina tipo da mensagem
    let messageType = "text";
    if (msg.hasMedia) {
      if (msg.type === "ptt" || msg.type === "audio") messageType = "audio";
      else if (msg.type === "image") messageType = "image";
      else if (msg.type === "document") messageType = "document";
      else if (msg.type === "sticker") messageType = "sticker";
      else messageType = msg.type;
    }

    // Conteudo: texto ou arquivo baixado
    let content = msg.body || "";

    if (msg.hasMedia) {
      try {
        const media = await msg.downloadMedia();
        if (media) {
          const ext =
            media.mimetype.split("/")[1]?.split(";")[0] || "bin";
          const filename = `${msg.id.id}.${ext}`;
          const filepath = path.join(MEDIA_DIR, filename);
          fs.writeFileSync(filepath, Buffer.from(media.data, "base64"));
          content = filepath;
          console.log(`[WhatsApp] Mídia salva: ${filepath}`);
        }
      } catch (err) {
        console.error("[WhatsApp] Erro ao baixar mídia:", err.message);
        content = "[erro ao baixar mídia]";
      }
    }

    const payload = {
      chat_id: chat.id._serialized,
      chat_name: chat.name || contact.pushname || contact.number,
      sender_phone: contact.number,
      sender_name: contact.pushname || contact.name || contact.number,
      message_id: msg.id.id,
      message_type: messageType,
      content: content,
      is_group: chat.isGroup,
      timestamp: msg.timestamp,
    };

    // Envia pro backend da Stormy
    const res = await fetch(STORMY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      console.error(`[WhatsApp] Stormy retornou ${res.status}`);
    }
  } catch (err) {
    console.error("[WhatsApp] Erro ao processar mensagem:", err.message);
  }
});

// ── Express API ─────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

// Status
app.get("/status", (_req, res) => {
  res.json({
    connected: clientReady,
    number: authenticatedNumber,
  });
});

// Enviar mensagem para contato
app.post("/send", async (req, res) => {
  const { phone, message } = req.body;
  if (!phone || !message) {
    return res.status(400).json({ error: "phone e message são obrigatórios" });
  }
  if (!clientReady) {
    return res.status(503).json({ error: "WhatsApp não conectado" });
  }

  try {
    // Formata número: remove +, espaços, hífens e adiciona @c.us
    const chatId = phone.replace(/[\s\-\+]/g, "") + "@c.us";
    await client.sendMessage(chatId, message);
    res.json({ ok: true, chat_id: chatId });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Enviar mensagem em grupo
app.post("/send_to_group", async (req, res) => {
  const { group_id, message } = req.body;
  if (!group_id || !message) {
    return res
      .status(400)
      .json({ error: "group_id e message são obrigatórios" });
  }
  if (!clientReady) {
    return res.status(503).json({ error: "WhatsApp não conectado" });
  }

  try {
    await client.sendMessage(group_id, message);
    res.json({ ok: true, group_id: group_id });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Start ───────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`[WhatsApp] API rodando em http://localhost:${PORT}`);
});

client.initialize();
