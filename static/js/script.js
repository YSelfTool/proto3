
function toggle_expansion() {
    var description_element = document.getElementById(this.id + "-description");
    var current_state = document.defaultView.getComputedStyle(description_element, "").getPropertyValue("display");
    var new_state = current_state == "none" ? "block" : "none";
    description_element.style.display = new_state;
};

var max_height = 400;
function resize_textarea(textarea) {
    function _inner_resize_textarea() {
        textarea.style.height = "auto";
        var new_height = textarea.scrollHeight;
        var overflow = "hidden";
        if (new_height > max_height) {
            new_height = max_height;
            overflow = "visible";
        }
        textarea.style.height = new_height + "px";
        textarea.style.overflow = overflow;
    }
    return _inner_resize_textarea
}
function resize_textarea_delayed(textarea) {
    function _inner_resize_textarea_delayed() {
        window.setTimeout(resize_textarea(textarea), 0);
    }
    return _inner_resize_textarea_delayed;
}

window.onload=function() {
    // toggle expansion
    var buttons = document.getElementsByClassName("expansion-button");
    for (var i = 0; i < buttons.length; i++) {
        var button = buttons[i];
        button.onclick = toggle_expansion;
    }
    // resize textarea
    var textareas = document.getElementsByTagName("textarea");
    for (var i = 0; i < textareas.length; i++) {
        var textarea = textareas[i];
        textarea.addEventListener("change", resize_textarea(textarea), false);
        textarea.addEventListener("cut", resize_textarea_delayed(textarea), false);
        textarea.addEventListener("paste", resize_textarea_delayed(textarea), false);
        textarea.addEventListener("drop", resize_textarea_delayed(textarea), false);
        textarea.addEventListener("keydown", resize_textarea_delayed(textarea), false);
        resize_textarea(textarea)();
    }
};
