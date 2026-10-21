<#--
  Étape caméra (authenticator face-recognition). Modes (attribut faceMode) :
  capture | rejected | locked | unavailable.
  La caméra n'est allumée qu'en mode capture, et coupée dès l'image prise : elle est
  éteinte sur toutes les autres pages. Pas de "${" dans le JS : FreeMarker l'interpréterait.
-->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=false; section>
  <#if section = "header">
    Reconnaissance faciale
  <#elseif section = "form">
    <form id="kc-face-form" action="${url.loginAction}" method="post">
      <#if faceMode == "capture">
        <p>Regardez la caméra puis cliquez sur « Vérifier mon visage ».</p>
        <video id="face-video" autoplay playsinline muted
               style="width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:8px;background:#111;transform:scaleX(-1)"></video>
        <#-- 480x360 : largement assez pour SFace (visage recadré en 112x112), et le formulaire
             reste sous la limite de taille de Keycloak (~128 Ko, sinon HTTP 413). -->
        <canvas id="face-canvas" width="480" height="360" hidden></canvas>
        <input type="hidden" name="image" id="face-image">
        <p id="face-msg" role="status" style="min-height:1.5em">${faceMessage}</p>
        <#if faceAttemptsLeft == 1>
          <p><strong>Dernier essai</strong> avant un blocage de 5 minutes.</p>
        </#if>
        <button type="button" id="face-capture" disabled
                class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}">
          Vérifier mon visage
        </button>
        <script>
          (function () {
            var video = document.getElementById("face-video");
            var button = document.getElementById("face-capture");
            var msg = document.getElementById("face-msg");
            var stream = null;

            function stop() {
              if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
              stream = null;
            }
            window.addEventListener("pagehide", stop);

            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
              msg.textContent = "Caméra indisponible : page à ouvrir en HTTPS (ou localhost).";
              return;
            }
            navigator.mediaDevices
              .getUserMedia({ video: { width: 640, height: 480, facingMode: "user" }, audio: false })
              .then(function (s) {
                stream = s;
                video.srcObject = s;
                button.disabled = false;
              })
              .catch(function () {
                msg.textContent = "Accès à la caméra refusé ou aucune caméra branchée.";
              });

            button.addEventListener("click", function () {
              var canvas = document.getElementById("face-canvas");
              canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
              var image = canvas.toDataURL("image/jpeg", 0.8);
              if (image.length > 100000) image = canvas.toDataURL("image/jpeg", 0.5);
              document.getElementById("face-image").value = image;
              button.disabled = true;
              stop();
              msg.textContent = "Vérification...";
              document.getElementById("kc-face-form").submit();
            });
          })();
        </script>
      <#else>
        <div role="alert" style="margin-bottom:1rem">
          <#if faceMode == "rejected">
            <p><strong>Visage non reconnu.</strong></p>
            <p>Vous pouvez recommencer une fois avant un blocage de 5 minutes.</p>
          <#elseif faceMode == "locked">
            <p><strong>Identifiant bloqué.</strong></p>
            <p>Trop d'échecs de reconnaissance faciale. Nouvel essai possible à
              <time id="face-locked" datetime="${faceLockedUntil}">${faceLockedUntil}</time>.</p>
            <script>
              (function () {
                var el = document.getElementById("face-locked");
                var d = new Date(el.getAttribute("datetime"));
                if (!isNaN(d)) el.textContent = d.toLocaleTimeString("fr-FR");
              })();
            </script>
          <#else>
            <p><strong>Reconnaissance faciale indisponible.</strong></p>
            <p>Connexion au back-office impossible pour le moment. Réessayez plus tard.</p>
          </#if>
        </div>
        <input type="hidden" name="restart" value="1">
        <button type="submit"
                class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}">
          Ressaisir l'identifiant
        </button>
      </#if>
    </form>
  </#if>
</@layout.registrationLayout>
