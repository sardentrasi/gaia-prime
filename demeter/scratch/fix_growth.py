import re
import os

path = r'c:\Project\demeter\templates\growth_log.html'
with open(path, 'r', encoding='utf-8') as f:
    h = f.read()

# Make sure we don't accidentally stack scripts
h = re.sub(r'<script>[\s\S]*?</script>\s*{% endblock %}', '{% endblock %}', h)

# Add ID to chat messages
h = h.replace(
    '<div class="flex-1 p-6 overflow-y-auto bg-surface-bright flex flex-col gap-6">',
    '<div id="page-chat-messages" class="flex-1 p-6 overflow-y-auto bg-surface-bright flex flex-col gap-6">'
)

# Convert input area to form
h = h.replace(
    '<div class="relative flex items-center">',
    '<form id="page-chat-form" class="relative flex items-center">'
)
h = h.replace(
    '</button>\n</div>',
    '</button>\n</form>'
)
# We also have to fix the exact input to add id and change type if needed.
# We find exactly:
h = h.replace(
    'placeholder="Ask Demeter about health trends, pathogens, or parameters..." type="text"/>',
    'placeholder="Ask Demeter about health trends, pathogens, or parameters..." type="text" id="page-chat-input" autocomplete="off" required/>'
)
# Fix button to type submit
h = re.sub(
    r'<button class="absolute right-2 h-10 w-10 bg-brand-green rounded-full flex items-center justify-center text-near-black hover:bg-brand-green-deep transition-colors">',
    r'<button type="submit" class="absolute right-2 h-10 w-10 bg-brand-green rounded-full flex items-center justify-center text-near-black hover:bg-brand-green-deep transition-colors">',
    h
)

# Add growth-list 
h = h.replace(
    '<div class="space-y-4 relative before:absolute before:inset-y-0 before:left-4 before:w-px before:bg-border-subtle">',
    '<div id="growth-list" class="space-y-4 relative before:absolute before:inset-y-0 before:left-4 before:w-px before:bg-border-subtle">'
)

script = '''
<script>
document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('page-chat-form');
    const chatInput = document.getElementById('page-chat-input');
    const chatMessages = document.getElementById('page-chat-messages');

    if(chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const msg = chatInput.value.trim();
            if (!msg) return;
            sendToAIConsultant(msg);
        });
    }

    async function sendToAIConsultant(msg) {
        addChatMessage(msg, true);
        chatInput.value = '';
        
        const loadingId = 'ai-load-' + Date.now();
        addChatLoading(loadingId);

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            });
            const data = await res.json();
            document.getElementById(loadingId).remove();
            
            let replyText = data.reply;
            if(!replyText && data.error) replyText = 'Error: ' + data.error; 
            
            addChatMessage(replyText, false);
        } catch (e) {
            if(document.getElementById(loadingId)) document.getElementById(loadingId).remove();
            addChatMessage('⚠️ Agronomist is offline. Check connection.', false);
        }
    }

    function addChatMessage(text, isUser) {
        const div = document.createElement('div');
        if (isUser) {
            div.className = 'flex gap-4 max-w-[85%] self-end flex-row-reverse';
            div.innerHTML = `
                <div class="h-8 w-8 rounded-full bg-surface-container overflow-hidden shrink-0 mt-1 border border-border-subtle border-2">
                    <span class="material-symbols-outlined text-sm flex items-center justify-center h-full w-full bg-near-black text-pure-white" data-icon="person">person</span>
                </div>
                <div class="bg-near-black text-pure-white rounded-2xl rounded-tr-sm p-4 shadow-[0_2px_4px_rgba(0,0,0,0.04)]">
                    <p class="font-body-base text-body-base">${text}</p>
                </div>
            `;
        } else {
            div.className = 'flex gap-4 max-w-[85%]';
            div.innerHTML = `
                <div class="h-8 w-8 rounded-full bg-brand-green-light flex items-center justify-center text-brand-green-deep shrink-0 mt-1">
                    <span class="material-symbols-outlined text-sm" data-icon="smart_toy">smart_toy</span>
                </div>
                <div class="bg-pure-white border border-border-subtle rounded-2xl rounded-tl-sm p-4 shadow-[0_2px_4px_rgba(0,0,0,0.02)] w-full">
                    <p class="font-body-base text-body-base text-near-black leading-relaxed">${text ? text.replace(/\\n/g, '<br>') : '...'}</p>
                </div>
            `;
        }
        if(chatMessages) {
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    function addChatLoading(id) {
        const div = document.createElement('div');
        div.id = id;
        div.className = 'flex gap-4 max-w-[85%]';
        div.innerHTML = `
            <div class="h-8 w-8 rounded-full bg-brand-green-light flex items-center justify-center text-brand-green-deep shrink-0 mt-1 animate-pulse">
                <span class="material-symbols-outlined text-sm" data-icon="smart_toy">smart_toy</span>
            </div>
            <div class="bg-pure-white border border-border-subtle rounded-2xl rounded-tl-sm p-4 shadow-[0_2px_4px_rgba(0,0,0,0.02)] w-full flex items-center">
                <p class="font-mono-code text-[10px] text-gray-400 tracking-widest animate-pulse">ANALYZING...</p>
            </div>
        `;
        if(chatMessages) {
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }
});
</script>
'''

if '{% endblock %}' in h:
    h = h.replace('{% endblock %}', script + '\n{% endblock %}')

with open(path, 'w', encoding='utf-8') as f:
    f.write(h)

print("Replacement complete")