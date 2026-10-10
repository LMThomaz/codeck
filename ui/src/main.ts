import "./styles/app.css";
import { mount } from "svelte";
import App from "./App.svelte";
import { isNative } from "./lib/native";
import { initTheme } from "./lib/theme";

initTheme();

// O Commitdeck é um app de desktop: fora da janela nativa (ex.: alguém abriu o endereço local num navegador) a tela
// não sobe — e a API também recusa, porque a chave da execução só existe dentro do app.
if (isNative() && window.COMMITDECK_TOKEN) mount(App, { target: document.getElementById("app")! });
else document.getElementById("app")!.innerHTML =
  '<div style="height:100%;display:grid;place-items:center;font:15px system-ui;color:#a7aec0;background:#0b0d12">Abra o Commitdeck pelo aplicativo.</div>';
