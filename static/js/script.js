
function toggle_expansion() {
    var description_element = document.getElementById(this.id + "-description");
    var current_state = document.defaultView.getComputedStyle(description_element, "").getPropertyValue("display");
    var new_state = current_state == "none" ? "block" : "none";
    description_element.style.display = new_state;
};

window.onload=function() {
    var buttons = document.getElementsByClassName("expansion-button");
    for (var i = 0; i < buttons.length; i++) {
        var button = buttons[i];
        button.onclick = toggle_expansion;
    }
};
