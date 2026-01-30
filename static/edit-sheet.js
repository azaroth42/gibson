
function openContactModal() {
    document.getElementById('contact-modal').style.display = 'flex';
    document.getElementById('contact-name').focus();
}

function closeContactModal() {
    document.getElementById('contact-modal').style.display = 'none';
    document.getElementById('contact-name').value = '';
    document.getElementById('contact-desc').value = '';
}

async function submitContact() {
    const name = document.getElementById('contact-name').value;
    const desc = document.getElementById('contact-desc').value;

    if (!name) {
        alert("Name is required");
        return;
    }

    try {
        const res = await fetch(`/characters/${charId}/contacts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, description: desc })
        });
        if (res.ok) {
            characterData = await res.json();
            renderAll();
            closeContactModal();
        } else {
            alert("Failed to create contact");
        }
    } catch (e) {
        console.error(e);
        alert("Error connecting to server");
    }
}

async function updateHealth(delta) {
    const currentHealth = characterData.health || 0;
    const maxHealth = characterData.max_health || 25;
    let newHealth = currentHealth + delta;
    if (newHealth < 0) newHealth = 0;
    if (newHealth > maxHealth) newHealth = maxHealth;

    try {
        const res = await fetch(`/characters/${charId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ health: newHealth })
        });
        if (res.ok) {
            characterData = await res.json();
            renderAll();
        }
    } catch (e) { console.error(e); }
}

async function handleStatChange(statKey, delta) {
    const dbKey = statKey.toLowerCase();
    const currentVal = characterData[dbKey] || 0;
    const newVal = currentVal + delta;

    if (newVal < -1 || newVal > 2) return;

    const tempStats = {
        tough: characterData.tough,
        cool: characterData.cool,
        sharp: characterData.sharp,
        style: characterData.style,
        chrome: characterData.chrome
    };
    tempStats[dbKey] = newVal;

    const values = Object.values(tempStats).sort((a, b) => b - a);
    const limit = [2, 1, 1, 0, -1];

    for (let i = 0; i < 5; i++) {
        if (values[i] > limit[i]) {
            alert("Stat distribution cannot exceed standard array (2, 1, 1, 0, -1) and max value is 2.");
            return;
        }
    }

    try {
        const body = {};
        body[dbKey] = newVal;
        const res = await fetch(`/characters/${charId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (res.ok) {
            await fetchCharacter();
        }
    } catch (e) { console.error(e); }
}

async function toggleItem(id) {
    const el = document.getElementById(`item-details-${id}`);
    const arrow = document.getElementById(`item-arrow-${id}`);
    if (el.style.display === 'none') {
        el.style.display = 'block';
        arrow.innerHTML = '▼';
    } else {
        el.style.display = 'none';
        arrow.innerHTML = '▶';
    }
}

async function saveItemUpdate(itemId, updateData) {
    try {
        const res = await fetch(`/characters/${charId}/items/${itemId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData)
        });
        if (res.ok) {
            characterData = await res.json();
            renderAll();
            // Keep details open if we just updated
            setTimeout(() => {
                const el = document.getElementById(`item-details-${itemId}`);
                const arrow = document.getElementById(`item-arrow-${itemId}`);
                if (el) {
                    el.style.display = 'block';
                    arrow.innerHTML = '▼';
                }
            }, 50);
        }
    } catch (e) { console.error(e); }
}

function addTag(itemId) {
    const input = document.getElementById(`item-tags-input-${itemId}`);
    const val = input.value.trim();
    if (!val) return;

    // Get current custom tags from data
    const item = characterData.items.find(i => i.id === itemId);
    if (!item) return;

    const newTags = [...(item.custom_tags || [])];
    if (!newTags.includes(val)) {
        newTags.push(val);
        saveItemUpdate(itemId, { tags: newTags });
    }
    input.value = '';
}

function removeTag(itemId, tagToRemove) {
    const item = characterData.items.find(i => i.id === itemId);
    if (!item) return;

    const newTags = (item.custom_tags || []).filter(t => t !== tagToRemove);
    saveItemUpdate(itemId, { tags: newTags });
}

function updateDescription(itemId) {
    const textarea = document.getElementById(`item-desc-${itemId}`);
    const newDesc = textarea.value;
    saveItemUpdate(itemId, { description: newDesc });
}

async function createLink(targetName) {
    try {
        const res = await fetch(`/characters/${charId}/links`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_name: targetName })
        });
        if (res.ok) {
            characterData = await res.json();
            renderAll();
        }
    } catch (e) { console.error(e); }
}

async function updateLink(linkId, newVal) {
    if (newVal < -3 || newVal > 3) return;

    try {
        const res = await fetch(`/characters/${charId}/links/${linkId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: newVal })
        });
        if (res.ok) {
            characterData = await res.json();
            renderAll();
        }
    } catch (e) { console.error(e); }
}

function toggleAdvance(key) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'action', action: 'toggle_advance', key: key }));
    }
}

async function deleteItem(itemId) {
    if (!confirm("Are you sure you want to delete this item?")) return;

    try {
        const res = await fetch(`/characters/${charId}/items/${itemId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            characterData = await res.json();
            renderAll();
        } else {
            alert("Failed to delete item");
        }
    } catch (e) {
        console.error(e);
        alert("Error deleting item");
    }
}
