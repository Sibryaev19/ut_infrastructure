import base64
import os
from IPython.display import display, HTML

# display(HTML(f'<style>{open("for_datalab/styles/all.css", "r").read()}</style>'))

def set_custom_spinner(image_path):
    if not os.path.exists(image_path):
        print(f"❌ Ошибка: Файл не найден по пути {image_path}")
        return

    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/gif" if ext == ".gif" else "image/webp" if ext == ".webp" else "image/png" if ext == ".png" else None
    
    if not mime:
        print(f"❌ Ошибка: Неподдерживаемое расширение '{ext}'")
        return

    with open(image_path, "rb") as f:
        base64_data = base64.b64encode(f.read()).decode('utf-8')
    
    data_uri = f"data:{mime};base64,{base64_data}"
    
    html_code = f"""
    <script>
    (function() {{
        // 1. Внедряем CSS (стили для гифки)
        let styleId = 'jp-custom-gif-style';
        let style = document.getElementById(styleId);
        if (!style) {{
            style = document.createElement('style');
            style.id = styleId;
            document.head.appendChild(style);
        }}
        style.innerHTML = `
            .jp-InputPrompt {{
                overflow: visible !important;
                text-overflow: clip !important;
                white-space: nowrap;
            }}
            .jp-custom-gif-spinner {{
                display: inline-block;
                width: 2.2em;
                height: 2.2em;
                background-image: url('{data_uri}');
                background-size: contain;
                background-repeat: no-repeat;
                background-position: center;
                vertical-align: middle;
                margin-left: 2px;
            }}
        `;

        // 2. Настраиваем MutationObserver
        if (window.customSpinnerObserver) {{
            window.customSpinnerObserver.disconnect();
        }}

        window.customSpinnerObserver = new MutationObserver(function(mutations) {{
            mutations.forEach(function(mutation) {{
                let prompt = mutation.target;
                
                // Поднимаемся к родителю, если изменение произошло в текстовом узле
                if (!prompt.classList || !prompt.classList.contains('jp-InputPrompt')) {{
                    prompt = prompt.closest('.jp-InputPrompt');
                }}
                if (!prompt) return;

                let text = prompt.textContent.trim();

                // Ячейка запустилась (есть звездочка, но еще нет нашего спан-а)
                if (text.includes('*') && !prompt.dataset.spinnerActive) {{
                    prompt.dataset.spinnerActive = 'true';
                    prompt.innerHTML = '[<span class="jp-custom-gif-spinner"></span>]:';
                }} 
                // Ячейка завершилась (звездочки нет, но раньше мы включали спиннер)
                else if (!text.includes('*') && prompt.dataset.spinnerActive) {{
                    delete prompt.dataset.spinnerActive;
                    // ВАЖНО: Мы НЕ трогаем innerHTML! JupyterLab уже сам записал туда цифру [N]:
                    // Мы просто убираем наш флаг. Observer не зациклится.
                }}
            }});
        }});

        // Следим за всем документом
        window.customSpinnerObserver.observe(document.body, {{
            childList: true,
            subtree: true,
            characterData: true
        }});

        console.log('✅ Спиннер установлен и Observer активирован.');
    }})();
    </script>
    """
    display(HTML(html_code))
    print(f"✅ Спиннер установлен из файла: {image_path}")