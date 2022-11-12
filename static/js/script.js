
function toggle_expansion() {
    var description_element = document.getElementById(this.id + "-description");
    var current_state = document.defaultView.getComputedStyle(description_element, "").getPropertyValue("display");
    var new_state = current_state == "none" ? "block" : "none";
    description_element.style.display = new_state;
};

var max_height = 400;
function resize_textarea(textarea) {
    function _inner_resize_textarea() {
        var current_height = textarea.style.height;
        var current_width = textarea.style.width;
        var use_current_height = (current_height != "") && Boolean(textarea.custom_height);
        textarea.style.height = "auto";
        var new_height = textarea.scrollHeight;
        var overflow = "hidden";
        if (new_height > max_height) {
            new_height = max_height;
            overflow = "visible";
        }
        var keep_height = false;
        if (use_current_height) {
            current_height = parseInt(current_height);
            if (current_height > new_height && current_height != textarea.custom_height) {
                keep_height = true;
            }
        }
        if (!keep_height) {
            textarea.style.height = new_height + "px";
            textarea.custom_height = new_height;
            textarea.style.overflow = overflow;
        } else {
            textarea.style.height = current_height + "px";
        }
    }
    return _inner_resize_textarea
}
function resize_textarea_delayed(textarea) {
    function _inner_resize_textarea_delayed() {
        window.setTimeout(resize_textarea(textarea), 0);
    }
    return _inner_resize_textarea_delayed;
}

function tab_on_key_down(textarea) {
    function _inner_tab_on_key_down(e) {
        if (e.keyCode == 9) {
            var start = textarea.selectionStart;
            var end = textarea.selectionEnd;
            var text = textarea.value;
            if (start == end) {
                var text_before = text.substring(0, start);
                var text_after = text.substring(end);
                textarea.value = text_before + "\t" + text_after;
                textarea.selectionStart = start+1;
                textarea.selectionEnd = end+1;
            } else {
                var text_before = text.substring(0, start);
                var text_center = text.substring(start, end);
                var text_after = text.substring(end);
                lines = text_center.split("\n");
                var forward = !e.shiftKey;
                var new_center = "";
                if (forward) {
                    for (var i = 0; i < lines.length; i++) {
                        new_center += "\t" + lines[i];
                        if (i != lines.length - 1) {
                            new_center += "\n";
                        }
                    }
                    textarea.value = text_before + new_center + text_after;
                    textarea.selectionStart = start;
                    textarea.selectionEnd = end + lines.length;
                } else {
                    var reduction = 0;
                    var start_reduction = 0;
                    for (var i = 0; i < lines.length; i++) {
                        var newline = lines[i];
                        if (newline[0] == "\t") {
                            newline = newline.substring(1);
                            reduction += 1;
                            if (i == 0) {
                                start_reduction += 1;
                            }
                        }
                        new_center += newline;
                        if (i != lines.length - 1) {
                            new_center += "\n";
                        }
                    }
                    textarea.value = text_before + new_center + text_after;
                    textarea.selectionStart = start - start_reduction;
                    textarea.selectionEnd = end - reduction;
                }
            }
            e.preventDefault();
        }
    }
    return _inner_tab_on_key_down;
}

window.onload=function() {
    // toggle expansion
    var buttons = document.getElementsByClassName("expansion-button");
    for (var i = 0; i < buttons.length; i++) {
        var button = buttons[i];
        button.onclick = toggle_expansion;
    }
    // resize of and tabs in textarea
    var textareas = document.getElementsByTagName("textarea");
    for (var i = 0; i < textareas.length; i++) {
        var textarea = textareas[i];
        var delayed = resize_textarea_delayed(textarea);
        var tab_func = tab_on_key_down(textarea);
        textarea.addEventListener("change", resize_textarea(textarea), false);
        textarea.addEventListener("cut", delayed, false);
        textarea.addEventListener("paste", delayed, false);
        textarea.addEventListener("drop", delayed, false);
        textarea.addEventListener("keydown", function(e){tab_func(e); delayed()}, false);
        resize_textarea(textarea)();
    }
    // confirm buttons
    for (var element of document.querySelectorAll('[confirm]')) {
        element.onclick = function(evt) {
            var target = evt.target;
            while (!target.hasAttribute("confirm")) {
                target = target.parentElement;
            }
            return confirm(target.getAttribute("confirm"));
        };
    }
};
